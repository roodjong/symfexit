from django.contrib import admin

from symfexit.documents.models import Directory, File


# Register your models here.
@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    pass


@admin.register(Directory)
class DirectoryAdmin(admin.ModelAdmin):
    pass
