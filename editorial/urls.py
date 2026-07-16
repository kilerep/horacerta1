from django.urls import path

from .feeds import LatestEditorialFeed
from . import views


app_name = "editorial"

urlpatterns = [
    path("", views.article_list, name="article_list"),
    path("feed.xml", LatestEditorialFeed(), name="feed"),
    path("politica-editorial/", views.editorial_policy, name="editorial_policy"),
    path("<slug:slug>/", views.article_detail, name="article_detail"),
]
