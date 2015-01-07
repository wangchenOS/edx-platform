import unittest
import decimal
import ddt
from django.conf import settings
from django.test.utils import override_settings
from django.core.urlresolvers import reverse

from xmodule.modulestore.tests.django_utils import (
    ModuleStoreTestCase, mixed_store_config
)

from xmodule.modulestore.tests.factories import CourseFactory
from courseware.tests.factories import InstructorFactory  # pylint: disable=F0401
from course_modes.tests.factories import CourseModeFactory
from student.tests.factories import CourseEnrollmentFactory, UserFactory
from student.models import CourseEnrollment


# Since we don't need any XML course fixtures, use a modulestore configuration
# that disables the XML modulestore.
from util.testing import UrlResetMixin

MODULESTORE_CONFIG = mixed_store_config(settings.COMMON_TEST_DATA_ROOT, {}, include_xml=False)


@ddt.ddt
@override_settings(MODULESTORE=MODULESTORE_CONFIG)
@unittest.skipUnless(settings.ROOT_URLCONF == 'lms.urls', 'Test only valid in lms')
class CourseModeViewTest(ModuleStoreTestCase):

    def setUp(self):
        super(CourseModeViewTest, self).setUp()
        self.course = CourseFactory.create()
        self.user = UserFactory.create(username="Bob", email="bob@example.com", password="edx")
        self.client.login(username=self.user.username, password="edx")

    @unittest.skipUnless(settings.ROOT_URLCONF == 'lms.urls', 'Test only valid in lms')
    @ddt.data(
        # is_active?, enrollment_mode, redirect?
        (True, 'verified', True),
        (True, 'honor', False),
        (True, 'audit', False),
        (False, 'verified', False),
        (False, 'honor', False),
        (False, 'audit', False),
        (False, None, False),
    )
    @ddt.unpack
    def test_redirect_to_dashboard(self, is_active, enrollment_mode, redirect):
        # Create the course modes
        for mode in ('audit', 'honor', 'verified'):
            CourseModeFactory(mode_slug=mode, course_id=self.course.id)

        # Enroll the user in the test course
        if enrollment_mode is not None:
            CourseEnrollmentFactory(
                is_active=is_active,
                mode=enrollment_mode,
                course_id=self.course.id,
                user=self.user
            )

        # Configure whether we're upgrading or not
        url = reverse('course_modes_choose', args=[unicode(self.course.id)])
        response = self.client.get(url)

        # Check whether we were correctly redirected
        if redirect:
            self.assertRedirects(response, reverse('dashboard'))
        else:
            self.assertEquals(response.status_code, 200)

    def test_upgrade_copy(self):
        # Create the course modes
        for mode in ('audit', 'honor', 'verified'):
            CourseModeFactory(mode_slug=mode, course_id=self.course.id)

        url = reverse('course_modes_choose', args=[unicode(self.course.id)])
        response = self.client.get(url, {"upgrade": True})

        # Verify that the upgrade copy is displayed instead
        # of the usual text.
        self.assertContains(response, "Upgrade Your Enrollment")

    def test_no_enrollment(self):
        # Create the course modes
        for mode in ('audit', 'honor', 'verified'):
            CourseModeFactory(mode_slug=mode, course_id=self.course.id)

        # User visits the track selection page directly without ever enrolling
        url = reverse('course_modes_choose', args=[unicode(self.course.id)])
        response = self.client.get(url)

        self.assertEquals(response.status_code, 200)

    @ddt.data(
        '',
        '1,,2',
        '1, ,2',
        '1, 2, 3'
    )
    def test_suggested_prices(self, price_list):

        # Create the course modes
        for mode in ('audit', 'honor'):
            CourseModeFactory(mode_slug=mode, course_id=self.course.id)

        CourseModeFactory(
            mode_slug='verified',
            course_id=self.course.id,
            suggested_prices=price_list
        )

        # Enroll the user in the test course to emulate
        # automatic enrollment
        CourseEnrollmentFactory(
            is_active=True,
            course_id=self.course.id,
            user=self.user
        )

        # Verify that the prices render correctly
        response = self.client.get(
            reverse('course_modes_choose', args=[unicode(self.course.id)]),
            follow=False,
        )

        self.assertEquals(response.status_code, 200)
        # TODO: Fix it so that response.templates works w/ mako templates, and then assert
        # that the right template rendered

    def test_professional_enrollment(self):
        # The only course mode is professional ed
        CourseModeFactory(mode_slug='professional', course_id=self.course.id)

        # Go to the "choose your track" page
        choose_track_url = reverse('course_modes_choose', args=[unicode(self.course.id)])
        response = self.client.get(choose_track_url)

        # Expect that we're redirected immediately to the "show requirements" page
        # (since the only available track is professional ed)
        show_reqs_url = reverse('verify_student_show_requirements', args=[unicode(self.course.id)])
        self.assertRedirects(response, show_reqs_url)

        # Now enroll in the course
        CourseEnrollmentFactory(
            user=self.user,
            is_active=True,
            mode="professional",
            course_id=unicode(self.course.id),
        )

        # Expect that this time we're redirected to the dashboard (since we're already registered)
        response = self.client.get(choose_track_url)
        self.assertRedirects(response, reverse('dashboard'))

    # Mapping of course modes to the POST parameters sent
    # when the user chooses that mode.
    POST_PARAMS_FOR_COURSE_MODE = {
        'honor': {'honor_mode': True},
        'verified': {'verified_mode': True, 'contribution': '1.23'},
        'unsupported': {'unsupported_mode': True},
    }

    @ddt.data(
        ('honor', 'dashboard'),
        ('verified', 'show_requirements'),
    )
    @ddt.unpack
    def test_choose_mode_redirect(self, course_mode, expected_redirect):
        # Create the course modes
        for mode in ('audit', 'honor', 'verified'):
            CourseModeFactory(mode_slug=mode, course_id=self.course.id)

        # Choose the mode (POST request)
        choose_track_url = reverse('course_modes_choose', args=[unicode(self.course.id)])
        response = self.client.post(choose_track_url, self.POST_PARAMS_FOR_COURSE_MODE[course_mode])

        # Verify the redirect
        if expected_redirect == 'dashboard':
            redirect_url = reverse('dashboard')
        elif expected_redirect == 'show_requirements':
            redirect_url = reverse(
                'verify_student_show_requirements',
                kwargs={'course_id': unicode(self.course.id)}
            ) + "?upgrade=False"
        else:
            self.fail("Must provide a valid redirect URL name")

        self.assertRedirects(response, redirect_url)

    def test_remember_donation_for_course(self):
        # Create the course modes
        for mode in ('honor', 'verified'):
            CourseModeFactory(mode_slug=mode, course_id=self.course.id)

        # Choose the mode (POST request)
        choose_track_url = reverse('course_modes_choose', args=[unicode(self.course.id)])
        self.client.post(choose_track_url, self.POST_PARAMS_FOR_COURSE_MODE['verified'])

        # Expect that the contribution amount is stored in the user's session
        self.assertIn('donation_for_course', self.client.session)
        self.assertIn(unicode(self.course.id), self.client.session['donation_for_course'])

        actual_amount = self.client.session['donation_for_course'][unicode(self.course.id)]
        expected_amount = decimal.Decimal(self.POST_PARAMS_FOR_COURSE_MODE['verified']['contribution'])
        self.assertEqual(actual_amount, expected_amount)

    def test_successful_honor_enrollment(self):
        # Create the course modes
        for mode in ('honor', 'verified'):
            CourseModeFactory(mode_slug=mode, course_id=self.course.id)

        # Enroll the user in the default mode (honor) to emulate
        # automatic enrollment
        params = {
            'enrollment_action': 'enroll',
            'course_id': unicode(self.course.id)
        }
        self.client.post(reverse('change_enrollment'), params)

        # Explicitly select the honor mode (POST request)
        choose_track_url = reverse('course_modes_choose', args=[unicode(self.course.id)])
        self.client.post(choose_track_url, self.POST_PARAMS_FOR_COURSE_MODE['honor'])

        # Verify that the user's enrollment remains unchanged
        mode, is_active = CourseEnrollment.enrollment_mode_for_user(self.user, self.course.id)
        self.assertEqual(mode, 'honor')
        self.assertEqual(is_active, True)

    def test_unsupported_enrollment_mode_failure(self):
        # Create the supported course modes
        for mode in ('honor', 'verified'):
            CourseModeFactory(mode_slug=mode, course_id=self.course.id)

        # Choose an unsupported mode (POST request)
        choose_track_url = reverse('course_modes_choose', args=[unicode(self.course.id)])
        response = self.client.post(choose_track_url, self.POST_PARAMS_FOR_COURSE_MODE['unsupported'])

        self.assertEqual(400, response.status_code)


@override_settings(MODULESTORE=MODULESTORE_CONFIG)
@unittest.skipUnless(settings.ROOT_URLCONF == 'lms.urls', 'Test only valid in lms')
class AddHonorModeToCourseTest(UrlResetMixin, ModuleStoreTestCase):
    """
    Unittests for course_modes.views.add_mode_to_course
    """

    def setUp(self):
        super(AddHonorModeToCourseTest, self).setUp()
        self.course = CourseFactory.create()
        self.instructor = InstructorFactory(course_key=self.course.id)
        self.client.login(username=self.instructor.username, password='test')
        self.url = reverse('add_mode_to_course', kwargs={'course_id': self.course.id.to_deprecated_string()})

    def test_add_mode_to_course(self):
        """
        test to add the honor mode for the course id
        """
        # get the course mode view
        response = self.client.get(self.url)
        self.assertEqual(200, response.status_code)

        data = {
            'course_mode': 'honor',
            'course_mode_display_name': 'Honor Display',
            'course_mode_price': '12',
            'course_mode_currency': 'usd'
        }
        response = self.client.post(self.url, data)
        self.assertEqual(200, response.status_code)
        self.assertEqual('success', response.content)

    def test_add_wrong_mode_to_course(self):
        """
        test to add the error mode for the course id
        """
        # get the course mode view
        response = self.client.get(self.url)
        self.assertEqual(200, response.status_code)

        data = {
            'course_mode': 'error_mode',
            'course_mode_display_name': 'Error Mode Display',
            'course_mode_price': '12',
            'course_mode_currency': 'usd'
        }
        response = self.client.post(self.url, data)
        self.assertEqual(400, response.status_code)
        self.assertEqual('Enter the available mode_slug for the course.', response.content)

    def test_fail_add_mode_to_course(self):
        """
        test that fails to create the course mode honor
        when not giving the proper course mode price
        """
        # get the course mode view
        response = self.client.get(self.url)
        self.assertEqual(200, response.status_code)

        data = {
            'course_mode': 'honor',
            'course_mode_display_name': 'Honor Display',
            'course_mode_price': '4wqe',
            'course_mode_currency': 'usd'
        }
        response = self.client.post(self.url, data)
        self.assertEqual(400, response.status_code)
        self.assertEqual('Enter the integer value for the price', response.content)
