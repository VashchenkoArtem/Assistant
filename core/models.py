from django.db import models

# Create your models here.

class AppCommand(models.Model):
    name = models.CharField(max_length= 100)
    path = models.CharField(max_length= 255, blank= True)
    aliases = models.CharField(max_length= 255, blank= True)

    def __str__(self):
        return f"Команда з назвою {self.name} та шляхом {self.path}"