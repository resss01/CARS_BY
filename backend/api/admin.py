from django.contrib import admin
from .models import Car_list

@admin.register(Car_list)
class Car_list_admin(admin.ModelAdmin):
    list_display = ('id', 'brand', 'model', 'engine', 'price_usd', 'price_byn', 'description', 'image')
    list_display_links = ('id', 'brand', 'model')
    search_fields = ('brand', 'model', 'description')
    list_filter = ('brand', 'model', 'engine', 'price_usd', 'price_byn')
    list_editable = ('price_usd', 'price_byn', 'description')
    list_per_page = 10
    list_max_show_all = 100

