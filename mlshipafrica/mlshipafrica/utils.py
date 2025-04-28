
import string
import random
from django.utils import timezone
from django.apps import apps




'''generateur code de reference'''
def CodeGenerator(model, start_by_text=None, end_by_text=None):

    if model == apps.get_model(app_label='core', model_name='License'): 
        start_by_text = "L{:%y}".format(timezone.now())

    if end_by_text is None:
        end_by_text = "{:%m%d}".format(timezone.now())       

    #CodeGenerator(Partie, "J{:%y}".format(timezone.now()), "{:%m%d}".format(timezone.now()))

    # Simuler un 'do-while' avec 'while True' et un 'break'
    while True:
        letters_and_digits = string.ascii_uppercase # + string.digits  # 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        code_letters = ''.join(random.choice(letters_and_digits) for _ in range(4))
        code = str(start_by_text) + str(code_letters) + str(end_by_text)
        count = model.objects.filter(code=code).count()
        if count > 0:
            pass
        else:
            return code