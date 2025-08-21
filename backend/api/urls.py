from django.urls import path
from . import views

urlpatterns = [
    path('cars/', views.Car_list_view.as_view()),
    path('cars/<int:pk>/', views.Car_detail_view.as_view()),
]