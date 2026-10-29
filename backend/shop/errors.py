from rest_framework.views import exception_handler as default_handler

FIELD_LABELS = {'name':'Nom','email':'Adresse e-mail','phone':'Téléphone','address':'Adresse','postal':'Code postal','city':'Ville','note':'Précision','password':'Mot de passe','label':'Nom de l’adresse','mode':'Mode de commande','items':'Panier','quantity':'Quantité','choices':'Options','productId':'Produit','paymentMethod':'Paiement','uid':'Lien','token':'Lien'}

def first_error(data, field=None):
    """First human message of a nested DRF error, with the field it belongs to."""
    if isinstance(data, str):
        return field, data
    if isinstance(data, list):
        for item in data:
            found = first_error(item, field)
            if found:
                return found
    if isinstance(data, dict):
        for key, value in data.items():
            found = first_error(value, field if key in {'non_field_errors', 'customer'} or str(key).isdigit() else key)
            if found:
                return found
    return None

def exception_handler(exc, context):
    response = default_handler(exc, context)
    if response is not None:
        if isinstance(response.data, dict) and isinstance(response.data.get('detail'), str):
            response.data = {'detail': str(response.data['detail'])}
        else:
            found = first_error(response.data)
            detail = 'Vérifiez les champs indiqués.'
            if found:
                field, message = found
                label = FIELD_LABELS.get(field, field)
                detail = f'{label} : {message}' if label else str(message)
            response.data = {'detail': detail, 'errors': response.data}
    return response
