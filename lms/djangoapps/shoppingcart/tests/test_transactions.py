"""
Tests for PaymentProcessorTransaction related models and logic
"""
from decimal import Decimal
import datetime
import sys
import uuid
from pytz import UTC

import smtplib
from boto.exception import BotoServerError  # this is a super-class of SESError and catches connection errors

from mock import patch, MagicMock
import pytz
import ddt
from django.core import mail
from django.conf import settings
from django.db import DatabaseError
from django.test import TestCase
from django.test.utils import override_settings
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError

from xmodule.modulestore.tests.django_utils import (
    ModuleStoreTestCase, mixed_store_config
)
from xmodule.modulestore.tests.factories import CourseFactory

from shoppingcart.models import (
    Order, OrderItem, PaidCourseRegistration, PaymentProcessorTransaction,
    TRANSACTION_TYPE_PURCHASE, TRANSACTION_TYPE_REFUND,
    PaymentTransactionCourseMap
)
from student.tests.factories import UserFactory
from student.models import CourseEnrollment
from course_modes.models import CourseMode
from shoppingcart.exceptions import (
    PurchasedCallbackException,
    CourseDoesNotExistException,
    ItemAlreadyInCartException,
    AlreadyEnrolledInCourseException,
    InvalidStatusToRetire,
    UnexpectedOrderItemStatus,
)

from opaque_keys.edx.locator import CourseLocator
from util.testing import UrlResetMixin

# Since we don't need any XML course fixtures, use a modulestore configuration
# that disables the XML modulestore.
MODULESTORE_CONFIG = mixed_store_config(settings.COMMON_TEST_DATA_ROOT, {}, include_xml=False)

@override_settings(MODULESTORE=MODULESTORE_CONFIG)
class PaymentProcessorTransactionModelTests(ModuleStoreTestCase):
    def setUp(self):
        """
        Set up testing environment
        """
        self.user = UserFactory.create()
        self.user2 = UserFactory.create()

        self.cost = 40.50
        self.course = CourseFactory.create()
        self.course_key = self.course.id
        self.course_mode = CourseMode(course_id=self.course_key,
                                      mode_slug="honor",
                                      mode_display_name="honor cert",
                                      min_price=self.cost)
        self.course_mode.save()

        self.course2 = CourseFactory.create()
        self.course_key2 = self.course2.id
        self.cost2 = 100.0
        self.course_mode2 = CourseMode(course_id=self.course_key2,
                                      mode_slug="honor",
                                      mode_display_name="honor cert",
                                      min_price=self.cost2)
        self.course_mode2.save()

        self.order1 = Order.get_cart_for_user(self.user)
        self.order_item1 = PaidCourseRegistration.add_to_order(self.order1, self.course_key)
        self.order1.purchase()

    def test_create_new_transaction(self):
        """
        Happy path testing of a new transaction
        """
        transaction = PaymentProcessorTransaction.create(
            uuid.uuid4(),
            uuid.uuid4(),
            datetime.datetime.now(pytz.UTC),
            self.order1.id,
            'USD',
            self.cost,
            TRANSACTION_TYPE_PURCHASE
        )

        # look up directly in database and assert that they are the same
        saved_transaction = PaymentProcessorTransaction.objects.get(remote_transaction_id = transaction.remote_transaction_id)
        self.assertEqual(transaction, saved_transaction)

        # then make sure there we can query against the mappings to the course
        queryset = PaymentProcessorTransaction.get_transactions_for_course(self.course_key)
        self.assertEqual(len(queryset), 1)
        self.assertEqual(queryset[0].transaction, transaction)

        queryset = PaymentProcessorTransaction.get_transactions_for_course(self.course_key, transaction_type=TRANSACTION_TYPE_PURCHASE)
        self.assertEqual(len(queryset), 1)
        self.assertEqual(queryset[0].transaction, transaction)

        queryset = PaymentProcessorTransaction.get_transactions_for_course(self.course_key, transaction_type=TRANSACTION_TYPE_REFUND)
        self.assertEqual(len(queryset), 0)

        # check some of the totals
        amounts = PaymentProcessorTransaction.get_transaction_totals_for_course(self.course_key)
        self.assertEqual(amounts['purchased'], self.cost)
        self.assertEqual(amounts['refunded'], 0.0)

    def test_multiple_transactions(self):
        """
        Similar happy path, but with multiple purchases, let's make sure the aggregate queries are correct.
        Interleave transactions between courses to make sure the GROUP BY is working as expected
        """
        PaymentProcessorTransaction.create(
            uuid.uuid4(),
            uuid.uuid4(),
            datetime.datetime.now(pytz.UTC),
            self.order1.id,
            'USD',
            self.cost,
            TRANSACTION_TYPE_PURCHASE
        )

        order2 = Order.get_cart_for_user(self.user2)
        PaidCourseRegistration.add_to_order(order2, self.course_key2)
        order2.purchase()

        PaymentProcessorTransaction.create(
            uuid.uuid4(),
            uuid.uuid4(),
            datetime.datetime.now(pytz.UTC),
            order2.id,
            'USD',
            self.cost2,
            TRANSACTION_TYPE_PURCHASE
        )

        order3 = Order.get_cart_for_user(self.user)
        PaidCourseRegistration.add_to_order(order3, self.course_key2)
        order3.purchase()

        PaymentProcessorTransaction.create(
            uuid.uuid4(),
            uuid.uuid4(),
            datetime.datetime.now(pytz.UTC),
            order3.id,
            'USD',
            self.cost2,
            TRANSACTION_TYPE_PURCHASE
        )

        order4 = Order.get_cart_for_user(self.user2)
        PaidCourseRegistration.add_to_order(order4, self.course_key)
        order4.purchase()

        PaymentProcessorTransaction.create(
            uuid.uuid4(),
            uuid.uuid4(),
            datetime.datetime.now(pytz.UTC),
            order4.id,
            'USD',
            self.cost,
            TRANSACTION_TYPE_PURCHASE
        )

        # check some of the totals
        amounts = PaymentProcessorTransaction.get_transaction_totals_for_course(self.course_key)
        self.assertEqual(amounts['purchased'], 2.0 * self.cost)
        self.assertEqual(amounts['refunded'], 0.0)

        amounts = PaymentProcessorTransaction.get_transaction_totals_for_course(self.course_key2)
        self.assertEqual(amounts['purchased'], 2.0 * self.cost2)
        self.assertEqual(amounts['refunded'], 0.0)

    def test_duplicate_same_transactions(self):
        """
        Test that we can create two transactions with the same primary key *AND* the same data
        """
        transaction = PaymentProcessorTransaction.create(
            uuid.uuid4(),
            uuid.uuid4(),
            datetime.datetime.now(pytz.UTC),
            self.order1.id,
            'USD',
            self.cost,
            TRANSACTION_TYPE_PURCHASE
        )

        # look up directly in database and assert that they are the same
        saved_transaction = PaymentProcessorTransaction.objects.get(remote_transaction_id = transaction.remote_transaction_id)
        self.assertEqual(transaction, saved_transaction)

        saved_transaction2 = PaymentProcessorTransaction.create(
                transaction.remote_transaction_id,
                transaction.account_id,
                transaction.processed_at,
                transaction.order.id,
                transaction.currency,
                transaction.amount,
                transaction.transaction_type
            )

        # these should be the same
        self.assertEqual(saved_transaction, saved_transaction2)

    def test_duplicate_different_transactions(self):
        """
        Test that we cannot create two transactions with the same primary key
        """
        transaction = PaymentProcessorTransaction.create(
            uuid.uuid4(),
            uuid.uuid4(),
            datetime.datetime.now(pytz.UTC),
            self.order1.id,
            'USD',
            self.cost,
            TRANSACTION_TYPE_PURCHASE
        )

        # look up directly in database and assert that they are the same
        saved_transaction = PaymentProcessorTransaction.objects.get(remote_transaction_id = transaction.remote_transaction_id)
        self.assertEqual(transaction, saved_transaction)

        with self.assertRaises(IntegrityError):
            PaymentProcessorTransaction.create(
                transaction.remote_transaction_id,
                uuid.uuid4(),
                datetime.datetime.now(pytz.UTC),
                self.order1.id,
                'USD',
                self.cost,
                TRANSACTION_TYPE_PURCHASE
            )

    def test_course_mapping_uniqueness(self):
        """
        Make sure we can't have multiple mappings of a transactions to courses
        """

        transaction = PaymentProcessorTransaction.create(
            uuid.uuid4(),
            uuid.uuid4(),
            datetime.datetime.now(pytz.UTC),
            self.order1.id,
            'USD',
            self.cost,
            TRANSACTION_TYPE_PURCHASE
        )

        mapping = PaymentTransactionCourseMap(
            transaction=transaction,
            course_id=self.course_key,
            order_item=self.order_item1
        )

        with self.assertRaises(IntegrityError):
            mapping.save()
