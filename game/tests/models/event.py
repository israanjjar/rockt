from django.test import TestCase
from django.contrib.auth.models import User

from game.models import Car, Stop, Event


class EventTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='joe',
                                        email='joe@bloggs.com',
                                        password='secret')
        self.user2 = User.objects.create(username='heidi',
                                         email='heidi@yahoo.com',
                                         password='idieh')
        self.bathurst_station = Stop.objects.create(
                            number='00112',
                            route='510',
                            location=[-79.411286, 43.666532],)
        self.bathurst_and_king = Stop.objects.create(
                            number='04412',
                            route='510',
                            location=[-79.402858, 43.644075],)
        self.car = Car.objects.create(
                                number=4211,
                                active=True,
                                location=[-79.402858, 43.644075],)
        self.car2 = Car.objects.create(
                                number=4212,
                                active=True,
                                location=[-79.402858, 43.644075],)
        self.car3 = Car.objects.create(
                                number=4012,
                                active=True,
                                location=[-79.402858, 43.644075],)

    def test_add_car_bought_data_correct(self):
        price = 150
        event = Event.objects.add_car_bought(self.car, self.user, price)
        self.assertEquals(event.event, 'car_bought')
        self.assertEquals(event.data['car'], self.car.number)
        self.assertEquals(event.data['user'], self.user.id)
        self.assertEquals(event.data['price'], price)

    def test_add_car_old_user_only_added_if_present(self):
        price = 150
        event = Event.objects.add_car_bought(self.car, self.user, price)
        self.assertNotIn('old_user', event.data)

        event = Event.objects.add_car_bought(self.car,
                                             self.user,
                                             price,
                                             self.user2)
        self.assertEquals(event.data['old_user'], self.user2.id)

    def test_add_car_sold_data_correct(self):
        price = 150
        event = Event.objects.add_car_sold(self.car, self.user, price)
        self.assertEquals(event.event, 'car_sold')
        self.assertEquals(event.data['car'], self.car.number)
        self.assertEquals(event.data['user'], self.user.id)
        self.assertEquals(event.data['price'], price)

    def test_add_car_ride_data_accurate(self):
        fare = 120
        event = Event.objects.add_car_ride(self.user, self.user2,
                                           self.car,
                                           self.bathurst_and_king,
                                           self.bathurst_station,
                                           fare,)
        make_dict = lambda stop: {'number': stop.number,
                                  'location': stop.location}
        expected = {
            'car': self.car.number,
            'rider': self.user.id,
            'on': make_dict(self.bathurst_and_king),
            'off': make_dict(self.bathurst_station),
            'fare': fare,
            'owner': self.user2.id}

        for key, val in expected.items():
            self.assertEquals(event.data[key], val)

        traveled = self.bathurst_station.distance_to(self.bathurst_and_king)
        self.assertAlmostEquals(event.data['traveled'], traveled)

    def test_add_car_ride_doesnt_add_owner_if_not_present(self):
        event = Event.objects.add_car_ride(self.user, None,
                                           self.car,
                                           self.bathurst_and_king,
                                           self.bathurst_station,
                                           0)
        self.assertNotIn('owner', event.data)

    def test_get_car_timeline_accurate(self):
        Event.objects.all().delete()
        price = 150
        e1 = Event.objects.add_car_bought(self.car, self.user, price)
        e2 = Event.objects.add_car_ride(self.user,
                                           None,
                                           self.car,
                                           self.bathurst_and_king,
                                           self.bathurst_station,
                                           0)
        e3 = Event.objects.add_car_ride(self.user, None,
                                           self.car2,
                                           self.bathurst_and_king,
                                           self.bathurst_station,
                                           0)
        e4 = Event.objects.add_car_sold(self.car, self.user, price)

        timeline = Event.objects.get_car_timeline(self.car)
        self.assertIn(e1, timeline)
        self.assertIn(e2, timeline)
        self.assertIn(e4, timeline)
        self.assertNotIn(e3, timeline)

    def test_get_car_timeline_data_user_is_username(self):
        Event.objects.all().delete()
        Event.objects.add_car_bought(self.car2, self.user, 10)
        Event.objects.add_car_ride(self.user, None,
                                           self.car2,
                                           self.bathurst_and_king,
                                           self.bathurst_station,
                                           0)
        timeline = Event.objects.get_car_timeline(self.car2)
        for event in timeline:
            if event.event == 'car_ride':
                self.assertEquals(event.data['rider'], self.user)
            if event.event == 'car_bought':
                self.assertEquals(event.data['user'], self.user)

    def test_get_car_timeline_data_deleted_user_is_none(self):
        Event.objects.all().all().delete()
        temp_user = User.objects.create(username='sarah',
                                        password="sarah@x.org")
        Event.objects.add_car_bought(self.car2, temp_user, 10)
        temp_user.delete()

        timeline = Event.objects.get_car_timeline(self.car2)
        self.assertIsNone(next(timeline).data['user'])
