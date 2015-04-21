__author__ = 'Omkareshwar'


__author__ = 'Omkareshwar'


from envelopes import Envelope, SMTP


class EmailAssistant:

    def __init__(self):
        pass


    def emailers(self, from_, to_, subject_, body_):
        envelope = Envelope(from_addr=from_,to_addr=to_,subject=subject_,text_body=body_)

        #TODO add password hashing
        smtpconn = SMTP(host='mail.nikitph.com',port=26,login='alpha@nikitph.com',password='davajvmasd123')
        print(smtpconn.is_connected)
        smtpconn.send(envelope)
