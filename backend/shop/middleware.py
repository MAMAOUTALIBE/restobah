import hashlib
import hmac
import ipaddress
import time
from datetime import timedelta
from django.conf import settings
from django.db import connection,OperationalError,transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from .models import AdminLoginAttempt

class AdminLoginThrottleMiddleware:
    """Rate limit admin login POSTs across workers, without storing raw IPs."""
    def __init__(self,get_response):
        self.get_response=get_response
    def __call__(self,request):
        if request.method=='POST' and request.path.rstrip('/') in {'/admin/login','/crm/connexion'}:
            blocked,retry_after=self.check(request)
            if blocked:
                detail='Trop de tentatives de connexion. Réessayez dans quelques minutes.'
                if request.path.rstrip('/')=='/crm/connexion':
                    from .crm_forms import StaffLoginForm
                    response=render(request,'shop/crm/login.html',{'form':StaffLoginForm(request=request),'rate_limit_error':detail,'demo_mode':settings.DEMO_MODE},status=429)
                    add_never_cache_headers(response)
                else:
                    response=JsonResponse({'detail':detail},status=429)
                response['Retry-After']=str(retry_after)
                return response
        return self.get_response(request)
    def check(self,request):
        remote=request.META.get('REMOTE_ADDR','unknown')
        candidate=request.META.get('HTTP_X_REAL_IP',remote) if settings.TRUST_PROXY else remote
        try:
            address=str(ipaddress.ip_address(candidate))
        except ValueError:
            address=remote
        key=hmac.new(settings.SECRET_KEY.encode(),address.encode(),hashlib.sha256).hexdigest()
        for attempt in range(6):
            try:
                return self.increment(key)
            except OperationalError as error:
                if connection.vendor!='sqlite' or 'locked' not in str(error).lower() or attempt==5:
                    raise
                time.sleep(0.025*(2**attempt))
    def increment(self,key):
        now=timezone.now()
        seconds=settings.ADMIN_LOGIN_WINDOW
        with transaction.atomic():
            # Keep the table bounded without retaining expired source identifiers.
            AdminLoginAttempt.objects.filter(window_started__lt=now-timedelta(seconds=seconds*2)).delete()
            counter,_=AdminLoginAttempt.objects.select_for_update().get_or_create(key=key,defaults={'window_started':now})
            if (now-counter.window_started).total_seconds()>=seconds:
                counter.count=0
                counter.window_started=now
            if counter.count>=settings.ADMIN_LOGIN_LIMIT:
                return True,max(1,int(seconds-(now-counter.window_started).total_seconds())+1)
            counter.count+=1
            counter.save(update_fields=['count','window_started'])
        return False,0
