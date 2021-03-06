from base64 import b64encode
import json

from django.test import TestCase
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse

from game.models import Car, Stop
from game.tests.utils import temporary_settings
from game.tests.views.api.common import ApiTests


class UserApiTest(ApiTests):
    api_name = 'user'

    def setUp(self):
        super(UserApiTest, self).setUp()

        self.car = Car.objects.create(number='4100', location=(0, 0))
        self.stop = Stop.objects.create(number='0',
                                        description='?',
                                        location=(0, 0))

    def test_auth_required(self):
        response = self.client.get(reverse(self.api_name))
        self.assertEquals(response.status_code, 403)

    def test_user_data_accurate(self):
        profile = self.user.get_profile()
        profile.balance = 100
        profile.save()

        response = self._make_get()
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEquals(data['username'], self.user.username)
        self.assertEquals(data['balance'], profile.balance)

    def test_not_checked_in_checkout_url_none(self):
        profile = self.user.get_profile()
        profile.riding = None
        profile.save()

        response = self._make_get()
        self.assertEquals(response.status_code, 200)
        data = json.loads(response.content)

        self.assertIsNone(data['check_out_url'])

    def test_checked_in_checkout_url_accurate(self):
        self.user.get_profile().check_in(self.car, self.stop)

        response = self._make_get()
        self.assertEquals(response.status_code, 200)
        data = json.loads(response.content)

        self.assertEquals(data['check_out_url'],
                          reverse('car-checkout'))


class UserCarListApiTests(ApiTests):
    api_name = 'user-car-list'

    def setUp(self):
        super(UserCarListApiTests, self).setUp()

        self.car1 = Car.objects.create(number='4001',
                                       location=(-79.4110, 43.66449))
        self.car2 = Car.objects.create(number='4002',
                                       location=(-79.4065, 43.66449))
        self.car3 = Car.objects.create(number='4003',
                                       location=(-79.3995, 43.63651))

    def test_auth_required(self):
        response = self.client.get(reverse(self.api_name))
        self.assertEquals(response.status_code, 403)

    def test_get_list_data_correct(self):
        def fake_price(*args, **kwargs):
            return 0
        with temporary_settings({'RULE_GET_STREETCAR_PRICE': fake_price}):
            self.car1.sell_to(self.user)
            self.car3.sell_to(self.user)

        expected_cars = {car.number: car for car in (self.car1,
                                                     self.car3)}
        response = self._make_get()
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEquals(len(data), 2)
        for car in data:
            self.assertIn(str(car['number']), expected_cars)
            expected = expected_cars[str(car['number'])]
            self.assertSequenceEqual(car['location'], expected.location)
            self.assertEquals(car['timeline_url'],
                              reverse('car-timeline', args=(car['number'],)))
            self.assertEquals(car['stats_url'],
                              reverse('user-car', args=(car['number'],)))


class UserCarApiTests(ApiTests):
    api_name = 'user-car'

    def setUp(self):
        super(UserCarApiTests, self).setUp()

        self.car = Car.objects.create(number='4010',
                                      route='510',
                                      location=[-79.30111, 43.68375])
        self.car.total_fares.revenue = 150
        self.car.total_fares.riders = 12
        self.car.owner_fares.revenue = 100
        self.car.owner_fares.riders = 2
        self.car.save()

    def test_auth_required(self):
        response = self.client.get(reverse(self.api_name, args=(0,)))
        self.assertEquals(response.status_code, 403)

    def test_not_owning_car_is_403(self):
        self.car.owner = None
        self.car.save()

        response = self._make_get((self.car.number,))
        self.assertStatusCode(response, 403)

    def test_data_is_accurate(self):
        self.car.owner = self.user.get_profile()
        self.car.save()

        response = self._make_get((self.car.number,))
        self.assertStatusCode(response, 200)
        data = json.loads(response.content)

        expected_fields = 'route', 'active', 'number', 'location'
        for field in expected_fields:
            self.assertIn(field, data)
            self.assertEquals(str(data[field]), str(getattr(self.car, field)))

        expected_fares = 'owner_fares', 'total_fares'
        for fare in expected_fares:
            self.assertIn(fare, data)
            expected_fare = getattr(self.car, fare)
            self.assertEquals(data[fare]['revenue'], expected_fare.revenue)
            self.assertEquals(data[fare]['riders'], expected_fare.riders)

        self.assertEquals(data['sell_car_url'],
                          reverse('car-buy', args=(self.car.number,)))
