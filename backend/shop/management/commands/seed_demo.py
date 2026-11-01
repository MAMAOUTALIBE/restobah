from datetime import time
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from shop.models import Restaurant,OpeningHour,Category,OptionGroup,Choice,Product
from shop.sequences import lock_seeded_tables, repair_crm_sequences

PRODUCTS=[
(1,'Le Bucket STC','Poulet','4 morceaux de poulet croustillant, frites et sauce au choix.','4 morceaux + frites + sauce au choix.','11.90','stc-menu-1','BEST-SELLER','4,9',False),
(2,'Le Menu Original','Menus','Burger poulet croustillant, frites et boisson au choix.','Burger poulet + frites + boisson.','15.90','stc-menu-2','LE BON PLAN','4,8',False),
(3,'Les Crispy Tenders','Poulet','5 tenders de poulet marinés, panure croustillante et sauce.','5 tenders de poulet + sauce au choix.','9.90','stc-menu-3','FAIT MAISON','4,9',False),
(4,'Les Frites Cheddar','Accompagnements','Frites dorées, cheddar fondant et oignons croustillants.','','5.50','fries','','4,8',True),
(5,'Le Veggie Garden','Burgers','Galette végétale, avocat, salade croquante et sauce aux herbes.','','10.90','veggie','','4,7',True),
(6,'Le Cookie Choco','Desserts','Cookie moelleux, généreux morceaux de chocolat noir.','','3.90','dessert','PETIT PLAISIR','4,9',True),
(7,'La Limonade Maison','Boissons','Citron pressé, menthe fraîche et fines bulles. 40 cl.','','4.50','drink','','4,8',True),
(8,'Le Spicy Chicken','Burgers','Poulet croustillant, coleslaw frais et sauce légèrement épicée.','','12.50','spicy','ÇA PIQUE !','4,8',False),
]
class Command(BaseCommand):
    help='Crée les données STC manquantes sans écraser les modifications de l’administration.'
    @transaction.atomic
    def handle(self,*args,**options):
        lock_seeded_tables()
        restaurant,created=Restaurant.objects.get_or_create(pk=1,defaults={'delivery_postal_codes':['75011','75010','75012','75020']})
        if created:
            OpeningHour.objects.bulk_create([OpeningHour(restaurant=restaurant,weekday=i,opens=time(11,30),closes=time(23)) for i in range(7)])
        categories={name:Category.objects.get_or_create(name=name,defaults={'position':i})[0] for i,name in enumerate(['Menus','Burgers','Poulet','Accompagnements','Boissons','Desserts'])}
        sauce,_=OptionGroup.objects.get_or_create(id='sauce',defaults={'name':'Votre sauce','minimum':1,'maximum':1})
        drink,_=OptionGroup.objects.get_or_create(id='drink',defaults={'name':'Votre boisson','minimum':1,'maximum':1})
        extras,_=OptionGroup.objects.get_or_create(id='extras',defaults={'name':'Un peu plus de plaisir ?','minimum':0,'maximum':3})
        for pk,group,name,price in [('sauce-maison',sauce,'Sauce maison','0'),('sauce-barbecue',sauce,'Barbecue','0'),('sauce-epicee',sauce,'Mayonnaise épicée','0'),('drink-cola',drink,'Cola 33 cl','0'),('drink-zero',drink,'Cola sans sucres 33 cl','0'),('drink-water',drink,'Eau minérale 50 cl','0'),('extra-cheddar',extras,'Cheddar supplémentaire','1.50'),('extra-bacon',extras,'Bacon croustillant','2.00'),('extra-sauce',extras,'Sauce maison','0.50')]:
            Choice.objects.get_or_create(id=pk,defaults={'group':group,'name':name,'price':Decimal(price)})
        for pk,name,category,description,summary,price,image,badge,rating,vegetarian in PRODUCTS:
            product,new=Product.objects.get_or_create(pk=pk,defaults={'name':name,'category':categories[category],'description':description,'summary':summary,'price':Decimal(price),'image':image,'badge':badge,'rating':rating,'vegetarian':vegetarian,'position':pk,'allergens':[] if pk==7 else ['gluten','lait','œufs']})
            if new:
                if pk in [1,3,5,8]:
                    product.option_groups.add(sauce)
                if pk==2:
                    product.option_groups.add(drink)
                if pk not in [6,7]:
                    product.option_groups.add(extras)
        original=Product.objects.get(pk=2)
        promotion,new=Product.objects.get_or_create(pk=90,defaults={'name':'Menu Original — Offre du moment','category':categories['Menus'],'description':'Burger poulet croustillant, frites et boisson au choix. Remise de 30 % incluse.','summary':'Le Menu Original à prix réduit.','price':Decimal('11.13'),'image':'stc-menu-2','badge':'−30 %','rating':'4,8','promotional':True,'promotion_source':original,'discount_percent':30,'position':90,'allergens':original.allergens})
        if new:
            promotion.option_groups.set(original.option_groups.all())
        repair_crm_sequences()
        self.stdout.write(self.style.SUCCESS('Catalogue STC prêt : données manquantes créées, données existantes conservées.'))
