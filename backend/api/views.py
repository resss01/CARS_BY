from rest_framework import generics
from .models import Car_list
from .serializers import Car_list_serializer
from django.views.generic import TemplateView

class Car_list_view(generics.ListCreateAPIView):
    queryset = Car_list.objects.all()
    serializer_class = Car_list_serializer

class Car_detail_view(generics.RetrieveUpdateDestroyAPIView):
    queryset = Car_list.objects.all()
    serializer_class = Car_list_serializer


