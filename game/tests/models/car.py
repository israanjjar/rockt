import datetime
import json

from django.test import TestCase
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse

from game.tests.utils import temporary_settings
from game.models import Car, Stop, UserProfile, FareInfo, Event
from game.rules import find_fare, get_streetcar_price, can_buy_car


class CarTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='joe',
                                        email='joe@bloggs.com',
                                        password='secret')
        self.user2 = User.objects.create(username='heidi',
                                         email='heidi@yahoo.com',
                                         password='idieh')

        def create_car(loc, number, route=511, active=True):
            return Car.objects.create(
                number=number,
                route=route,
                active=active,
                location=loc,)

        self.closest = create_car((-79.4110, 43.66449), 4211)
        self.closer = create_car((-79.4065, 43.66449), 4212)
        self.close = create_car((-79.39951, 43.63651), 4213)

        self.off_bathurst = create_car((-79.39629, 43.64858), 4123, 510)
        self.inactive = create_car((-79.40405, 43.64729), 4124, active=False)

        self.bathurst_station = Stop.objects.create(
                            number="00258",
                            location=[-79.411286, 43.666532],
                            route=511)
        self.bathurst_and_king = Stop.objects.create(
                            location=[-79.402858, 43.644075],
                            route=511)

    def test_sell_to_not_allowed_raises_exception(self):
        # This is not ideal, as we're duplicating testing for rules.py
        def fake_rule(*args, **kwargs):
            return False
        with temporary_settings({'RULE_CAN_BUY_CAR': fake_rule}):
            with self.assertRaises(Car.NotAllowedException):
                self.close.sell_to(self.user)

    def test_sell_to_with_insufficient_funds_raises_exception(self):
        profile = self.user.get_profile()
        profile.balance = 0
        profile.save()
        with self.assertRaises(UserProfile.InsufficientFundsException):
            self.close.sell_to(self.user)

    def test_sell_to(self):
        price = 65
        difference = 50

        def fake_price(*args, **kwargs):
            return price
        with temporary_settings({'RULE_GET_STREETCAR_PRICE': fake_price}):
            profile = self.user.get_profile()
            new_balance = price + difference
            profile.balance = new_balance
            profile.save()

            self.close.owner_fares = FareInfo(riders=10, revenue=15)
            self.close.sell_to(self.user)
            self.assertEqual(profile.balance, difference)
            self.assertEqual(self.close.owner_fares.riders, 0)
            self.assertEqual(self.close.owner_fares.revenue, 0)
            self.assertEqual(self.close.owner, profile)

    def test_sell_to_creates_event(self):
        def fake_price(*args, **kwargs):
            return 0
        with temporary_settings({'RULE_GET_STREETCAR_PRICE': fake_price}):
            self.close.sell_to(self.user)
            self.assertEventCreated('car_bought', self.close)

    def test_buy_back_wrong_user_throws_exception(self):
        self.close.owner = self.user.get_profile()
        self.close.save()

        with self.assertRaises(Car.NotAllowedException):
            self.close.buy_back(self.user2)

    def test_buy_back_credits_account(self):
        price = 65
        profile = self.user.get_profile()
        expected_balance = profile.balance + price

        def fake_price(*args, **kwargs):
            return price
        with temporary_settings({'RULE_GET_STREETCAR_PRICE': fake_price}):
            self.close.owner = profile
            self.close.save()
            self.close.buy_back(self.user)

            self.assertEqual(profile.balance, expected_balance)
            self.assertEqual(self.close.owner_fares.riders, 0)
            self.assertEqual(self.close.owner_fares.revenue, 0)
            self.assertEqual(self.close.owner, None)

    def test_buy_back_creates_event(self):
        self.close.owner = self.user.get_profile()
        self.close.save()
        self.close.buy_back(self.user)

        self.assertEventCreated('car_sold', self.close)

    def assertEventCreated(self, event_name, car):
        event = Event.objects.filter(event=event_name)[0]
        self.assertAlmostEquals(datetime.datetime.now(),
                                event.date,
                                delta=datetime.timedelta(seconds=1))
        self.assertEquals(event.data['car'], car.number)

    def test_find_nearby(self):
        nearby = Car.objects.find_nearby(self.bathurst_station).all()

        self.assertSequenceEqual(nearby, [self.closest,
                                          self.closer,
                                          self.close])

    def test_ride_insufficient_fare_throws_exception(self):
        profile = self.user.get_profile()
        profile.balance = 0
        with self.assertRaises(UserProfile.InsufficientFundsException):
            self.close.ride(self.user,
                            self.bathurst_station,
                            self.bathurst_and_king)

    def test_ride(self):
        fare = 50
        offset = 10
        profile = self.user.get_profile()
        profile.balance = fare + offset
        owner_profile = self.user2.get_profile()
        self.close.owner_fares = FareInfo()
        self.close.owner = owner_profile

        original_riders = 1
        original_revenue = 15
        self.close.total_fares = FareInfo(riders=original_riders,
                                          revenue=original_revenue)

        def fake_fare(*args, **kwargs):
            return fare

        expected_rider_balance = profile.balance - fare
        expected_owner_balance = owner_profile.balance + fare
        with temporary_settings({'RULE_FIND_FARE': fake_fare}):
            self.assertEquals(self.close.ride(self.user,
                                   self.bathurst_station,
                                   self.bathurst_and_king),
                               fare)

        self.assertEqual(self.user.get_profile().balance,
            expected_rider_balance)
        self.assertEqual(self.user2.get_profile().balance,
            expected_owner_balance)
        self.assertEqual(self.close.owner_fares.riders, 1)
        self.assertEqual(self.close.owner_fares.revenue, fare)
        self.assertEqual(self.close.total_fares.riders, original_riders + 1)
        self.assertEqual(self.close.total_fares.revenue,
                        original_revenue + fare)

    def test_ride_creates_event(self):
        #Ensure no fare issues
        self.close.owner = self.user.get_profile()
        self.close.save()

        self.close.ride(self.user,
                        self.bathurst_station,
                        self.bathurst_and_king)

        event = Event.objects.filter(event='car_ride')[0]

        self.assertAlmostEquals(datetime.datetime.now(),
                                event.date,
                                delta=datetime.timedelta(seconds=1))
        self.assertEquals(event.data['car'], self.close.number)
        self.assertEquals(event.data['rider'], self.user.id)
        self.assertFalse(can_buy_car(self.user, self.close))
