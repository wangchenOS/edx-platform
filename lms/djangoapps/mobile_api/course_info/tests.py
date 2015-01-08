"""
Tests for course_info
"""

import ddt
from django.conf import settings

from xmodule.html_module import CourseInfoModule
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.django import modulestore
from xmodule.modulestore.xml_importer import import_from_xml

from ..testutils import (
    MobileAPITestCase, MobileCourseAccessTestMixin, MobileEnrolledCourseAccessTestMixin, MobileAuthTestMixin
)


class TestAbout(MobileAPITestCase, MobileAuthTestMixin, MobileCourseAccessTestMixin):
    """
    Tests for /api/mobile/v0.5/course_info/{course_id}/about
    """
    REVERSE_INFO = {'name': 'course-about-detail', 'params': ['course_id']}

    def verify_success(self, response):
        super(TestAbout, self).verify_success(response)
        self.assertTrue('overview' in response.data)

    def init_course_access(self, course_id=None):
        # override this method since enrollment is not required for the About endpoint.
        self.login()

    def test_about_static_rewrite(self):
        self.login()

        about_usage_key = self.course.id.make_usage_key('about', 'overview')
        about_module = modulestore().get_item(about_usage_key)
        underlying_about_html = about_module.data

        # check that we start with relative static assets
        self.assertIn('\"/static/', underlying_about_html)

        # but shouldn't finish with any
        response = self.api_response()
        self.assertNotIn('\"/static/', response.data['overview'])


@ddt.ddt
class TestUpdates(MobileAPITestCase, MobileAuthTestMixin, MobileEnrolledCourseAccessTestMixin):
    """
    Tests for /api/mobile/v0.5/course_info/{course_id}/updates
    """
    REVERSE_INFO = {'name': 'course-updates-list', 'params': ['course_id']}

    def verify_success(self, response):
        super(TestUpdates, self).verify_success(response)
        self.assertEqual(response.data, [])

    @ddt.data(True, False)
    def test_updates(self, new_format):
        """
        Tests updates endpoint with /static in the content.
        Tests both new updates format (using "items") and old format (using "data").
        """
        self.login_and_enroll()

        # create course Updates item in modulestore
        updates_usage_key = self.course.id.make_usage_key('course_info', 'updates')
        course_updates = modulestore().create_item(
            self.user.id,
            updates_usage_key.course_key,
            updates_usage_key.block_type,
            block_id=updates_usage_key.block_id
        )

        # store content in Updates item (either new or old format)
        if new_format:
            course_update_data = {
                "id": 1,
                "date": "Some date",
                "content": "<a href=\"/static/\">foo</a>",
                "status": CourseInfoModule.STATUS_VISIBLE
            }
            course_updates.items = [course_update_data]
        else:
            update_data = u"<ol><li><h2>Date</h2><a href=\"/static/\">foo</a></li></ol>"
            course_updates.data = update_data
        modulestore().update_item(course_updates, self.user.id)

        # call API
        response = self.api_response()
        content = response.data[0]["content"]  # pylint: disable=maybe-no-member

        # verify static URLs are replaced in the content returned by the API
        self.assertNotIn("\"/static/", content)

        # verify static URLs remain in the underlying content
        underlying_updates = modulestore().get_item(updates_usage_key)
        underlying_content = underlying_updates.items[0]['content'] if new_format else underlying_updates.data
        self.assertIn("\"/static/", underlying_content)


class TestHandouts(MobileAPITestCase, MobileAuthTestMixin, MobileEnrolledCourseAccessTestMixin):
    """
    Tests for /api/mobile/v0.5/course_info/{course_id}/handouts
    """
    REVERSE_INFO = {'name': 'course-handouts-list', 'params': ['course_id']}

    def setUp(self):
        super(TestHandouts, self).setUp()

        # use toy course with handouts, and make it mobile_available
        course_items = import_from_xml(self.store, self.user.id, settings.COMMON_TEST_DATA_ROOT, ['toy'])
        self.course = course_items[0]
        self.course.mobile_available = True
        self.store.update_item(self.course, self.user.id)

    def verify_success(self, response):
        super(TestHandouts, self).verify_success(response)
        self.assertIn('Sample', response.data['handouts_html'])

    def test_no_handouts(self):
        self.login_and_enroll()

        # delete handouts in course
        handouts_usage_key = self.course.id.make_usage_key('course_info', 'handouts')
        with self.store.branch_setting(ModuleStoreEnum.Branch.draft_preferred, self.course.id):
            self.store.delete_item(handouts_usage_key, self.user.id)

        self.api_response(expected_response_code=404)

    def test_handouts_static_rewrites(self):
        self.login_and_enroll()

        # check that we start with relative static assets
        handouts_usage_key = self.course.id.make_usage_key('course_info', 'handouts')
        underlying_handouts = self.store.get_item(handouts_usage_key)
        self.assertIn('\'/static/', underlying_handouts.data)

        # but shouldn't finish with any
        response = self.api_response()
        self.assertNotIn('\'/static/', response.data['handouts_html'])
