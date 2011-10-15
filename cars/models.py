from django.db import models
from pymongo import GEO2D
from geopy.distance import distance
from djangotoolbox.fields import ListField,EmbeddedModelField 
from django_mongodb_engine.contrib import MongoDBManager


MAX_DISTANCE = ''
STREETCAR_PRICE = 400
STREETCAR_FARE_RATE = 2

# Create your models here.

class FareInfo(models.Model):
    riders = models.IntegerField(default=0)
    revenue = models.IntegerField(default=0)

class CarLocatorManager(MongoDBManager):
    def find_nearby(self,route, location):
        return self.raw_query({'location':
                                {'$maxDistance':MAX_DISTANCE,'$near':location},
                                'route':route})

class Car(models.Model):
    #Location information fields
    number = models.PositiveIntegerField(db_index=True)
    route = models.IntegerField(null=True)
    active = models.BooleanField()
    location = ListField() #(lon, lat)

    #Financial information fields 
    owner = models.ForeignKey('users.UserProfile',null=True)
    owner_fares = EmbeddedModelField(FareInfo)
    total_fares = EmbeddedModelField(FareInfo)
    
    
    objects = CarLocatorManager()

    def sell_to(self,user):
        profile = user.get_profile()
        if profile.balance < STREETCAR_PRICE:
            raise UserProfile.InsufficientFundsException
        self.owner = profile
        self.owner_fares = FareInfo()
        self.save()
        profile.balance -= STREETCAR_PRICE
        profile.save()
    
    def ride(self,user,on,off):
        #You don't have to pay for your own streetcars
        if user == self.owner:
            fare_paid = 0
        else:
           #geopy is lat,lon, mongo is lon,lat
           traveled = distance(*(car.location[::-1] for car in (on,off))) 
           fare_paid = round(traveled.kilometers * STREETCAR_FARE_RATE)

        for fare_info in (self.owner_fares,self.total_fares):
            fare_info.riders += 1
            fare_info.revenue += fare_paid 
        self.save()

        profile = user.get_profile()
        profile.balance -= fare_paid
        profile.save()


             
    class MongoMeta:
        indexes = [{'fields': [('location',GEO2D),'route']}]
