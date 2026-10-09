from django.contrib import admin
from .models import AppCommand

# Register your models here.
admin.site.register(AppCommand)
class AppCommandAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "path", "keywords", "added_automatically")
    list_filter = ("category", "added_automatically")
    search_fields = ("name", "keywords")
