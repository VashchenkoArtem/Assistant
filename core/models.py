from django.db import models

# Create your models here.

class AppCommand(models.Model):
    class Category(models.TextChoices):
        BROWSER = "browser", "Браузер"
        MESSENGER = "messenger", "Месенджер"
        GAME = "game", "Гра"
        MEDIA = "media", "Медіа/музика/відео"
        UTILITY = "utility", "Стандартна програма/утиліта"
        DEV_TOOL = "dev_tool", "Інструмент розробника"
        OTHER = "other", "Інше"

    name = models.CharField(max_length= 100)
    path = models.CharField(max_length= 255, blank= True)
    category = models.CharField(
        max_length= 20, 
        choices= Category.choices,
        default= Category.OTHER    
    )
    keywords = models.CharField(max_length= 255, blank= True)
    aliases = models.CharField(max_length= 255, blank= True)
    added_automatically = models.BooleanField(default= False)

    def __str__(self):
        return f"Команда з назвою {self.name} та шляхом {self.path}"