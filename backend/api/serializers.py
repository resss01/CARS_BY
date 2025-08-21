from rest_framework import serializers
from .models import Car_list

class Car_list_serializer(serializers.ModelSerializer):
    class Meta:
        model = Car_list
        fields = '__all__'