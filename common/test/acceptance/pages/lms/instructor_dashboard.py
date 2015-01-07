# -*- coding: utf-8 -*-
"""
Instructor (2) dashboard page.
"""

from bok_choy.page_object import PageObject
from .course_page import CoursePage
from .instructor_dashboard_paid_course_registrations import ECommercePage
import os


class InstructorDashboardPage(CoursePage):
    """
    Instructor dashboard, where course staff can manage a course.
    """
    url_path = "instructor"

    def is_browser_on_page(self):
        return self.q(css='div.instructor-dashboard-wrapper-2').present

    def select_membership(self):
        """
        Selects the membership tab and returns the MembershipSection
        """
        self.q(css='a[data-section=membership]').first.click()
        membership_section = MembershipPage(self.browser)
        membership_section.wait_for_page()
        return membership_section

    def select_ecommerce(self):
        """
        Selects the E-Commerce tab and returns an instance of the ECommercePage
        """
        self.q(css='a[data-section=e-commerce]').first.click()
        ecommerce_section = ECommercePage(self.browser)
        ecommerce_section.wait_for_page()
        return ecommerce_section

    def select_data_download(self):
        """
        Selects the data download tab and returns a DataDownloadPage.
        """
        self.q(css='a[data-section=data_download]').first.click()
        data_download_section = DataDownloadPage(self.browser)
        data_download_section.wait_for_page()
        return data_download_section

    @staticmethod
    def get_asset_path(file_name):
        """
        Returns the full path of the file to upload.
        These files have been placed in edx-platform/common/test/data/uploads/
        """

        # Separate the list of folders in the path reaching to the current file,
        # e.g.  '... common/test/acceptance/pages/lms/instructor_dashboard.py' will result in
        #       [..., 'common', 'test', 'acceptance', 'pages', 'lms', 'instructor_dashboard.py']
        folders_list_in_path = __file__.split(os.sep)

        # Get rid of the last 4 elements: 'acceptance', 'pages', 'lms', and 'instructor_dashboard.py'
        # to point to the 'test' folder, a shared point in the path's tree.
        folders_list_in_path = folders_list_in_path[:-4]

        # Append the folders in the asset's path
        folders_list_in_path.extend(['data', 'uploads', file_name])

        # Return the joined path of the required asset.
        return os.sep.join(folders_list_in_path)


class MembershipPage(PageObject):
    """
    Membership section of the Instructor dashboard.
    """
    url = None

    def is_browser_on_page(self):
        return self.q(css='a[data-section=membership].active-section').present

    def select_auto_enroll_section(self):
        """
        Returns the MembershipPageAutoEnrollSection page object.
        """
        return MembershipPageAutoEnrollSection(self.browser)

    def select_cohort_management_section(self):
        """
        Returns the MembershipPageCohortManagementSection page object.
        """
        return MembershipPageCohortManagementSection(self.browser)


class MembershipPageCohortManagementSection(PageObject):
    """
    The cohort management subsection of the Membership section of the Instructor dashboard.
    """
    url = None
    csv_browse_button_selector = '.csv-upload #file-upload-form-file'
    csv_upload_button_selector = '.csv-upload #file-upload-form-submit'

    def is_browser_on_page(self):
        return self.q(css='.cohort-management.membership-section').present

    def _bounded_selector(self, selector):
        """
        Return `selector`, but limited to the cohort management context.
        """
        return '.cohort-management.membership-section {}'.format(selector)

    def _get_cohort_options(self):
        """
        Returns the available options in the cohort dropdown, including the initial "Select a cohort group".
        """
        return self.q(css=self._bounded_selector("#cohort-select option"))

    def _cohort_name(self, label):
        """
        Returns the name of the cohort with the count information excluded.
        """
        return label.split(' (')[0]

    def _cohort_count(self, label):
        """
        Returns the count for the cohort (as specified in the label in the selector).
        """
        return int(label.split(' (')[1].split(')')[0])

    def get_cohorts(self):
        """
        Returns, as a list, the names of the available cohorts in the drop-down, filtering out "Select a cohort group".
        """
        return [
            self._cohort_name(opt.text)
            for opt in self._get_cohort_options().filter(lambda el: el.get_attribute('value') != "")
        ]

    def get_selected_cohort(self):
        """
        Returns the name of the selected cohort.
        """
        return self._cohort_name(
            self._get_cohort_options().filter(lambda el: el.is_selected()).first.text[0]
        )

    def get_selected_cohort_count(self):
        """
        Returns the number of users in the selected cohort.
        """
        return self._cohort_count(
            self._get_cohort_options().filter(lambda el: el.is_selected()).first.text[0]
        )

    def select_cohort(self, cohort_name):
        """
        Selects the given cohort in the drop-down.
        """
        self.q(css=self._bounded_selector("#cohort-select option")).filter(
            lambda el: self._cohort_name(el.text) == cohort_name
        ).first.click()

    def add_cohort(self, cohort_name):
        """
        Adds a new manual cohort with the specified name.
        """
        self.q(css=self._bounded_selector("div.cohort-management-nav .action-create")).first.click()
        textinput = self.q(css=self._bounded_selector("#cohort-create-name")).results[0]
        textinput.send_keys(cohort_name)
        self.q(css=self._bounded_selector("div.form-actions .action-save")).first.click()

    def get_cohort_group_setup(self):
        """
        Returns the description of the current cohort
        """
        return self.q(css=self._bounded_selector('.cohort-management-group-setup .setup-value')).first.text[0]

    def select_edit_settings(self):
        self.q(css=self._bounded_selector(".action-edit")).first.click()

    def add_students_to_selected_cohort(self, users):
        """
        Adds a list of users (either usernames or email addresses) to the currently selected cohort.
        """
        textinput = self.q(css=self._bounded_selector("#cohort-management-group-add-students")).results[0]
        for user in users:
            textinput.send_keys(user)
            textinput.send_keys(",")
        self.q(css=self._bounded_selector("div.cohort-management-group-add .action-primary")).first.click()

    def get_cohort_student_input_field_value(self):
        """
        Returns the contents of the input field where students can be added to a cohort.
        """
        return self.q(
            css=self._bounded_selector("#cohort-management-group-add-students")
        ).results[0].get_attribute("value")

    def _get_cohort_messages(self, type):
        """
        Returns array of messages related to manipulating cohorts directly through the UI for the given type.
        """
        title_css = "div.cohort-management-group-add .cohort-" + type + " .message-title"
        detail_css = "div.cohort-management-group-add .cohort-" + type + " .summary-item"

        return self._get_messages(title_css, detail_css)

    def get_csv_messages(self):
        """
        Returns array of messages related to a CSV upload of cohort assignments.
        """
        title_css = ".csv-upload .message-title"
        detail_css = ".csv-upload .summary-item"
        return self._get_messages(title_css, detail_css)

    def _get_messages(self, title_css, details_css):
        """
        Helper method to get messages given title and details CSS.
        """
        message_title = self.q(css=self._bounded_selector(title_css))
        if len(message_title.results) == 0:
            return []
        messages = [message_title.first.text[0]]
        details = self.q(css=self._bounded_selector(details_css)).results
        for detail in details:
            messages.append(detail.text)
        return messages

    def get_cohort_confirmation_messages(self):
        """
        Returns an array of messages present in the confirmation area of the cohort management UI.
        The first entry in the array is the title. Any further entries are the details.
        """
        return self._get_cohort_messages("confirmations")

    def get_cohort_error_messages(self):
        """
        Returns an array of messages present in the error area of the cohort management UI.
        The first entry in the array is the title. Any further entries are the details.
        """
        return self._get_cohort_messages("errors")

    def select_data_download(self):
        """
        Click on the link to the Data Download Page.
        """
        self.q(css=self._bounded_selector("a.link-cross-reference[data-section=data_download]")).first.click()

    def upload_cohort_file(self, filename):
        """
        Uploads a file with cohort assignment information.
        """
        # If the CSV upload section has not yet been toggled on, click on the toggle link.
        cvs_upload_toggle = self.q(css=self._bounded_selector(".toggle-cohort-management-secondary")).first
        if cvs_upload_toggle:
            cvs_upload_toggle.click()
        path = InstructorDashboardPage.get_asset_path(filename)
        file_input = self.q(css=self._bounded_selector(self.csv_browse_button_selector)).results[0]
        file_input.send_keys(path)
        self.q(css=self._bounded_selector(self.csv_upload_button_selector)).first.click()


class MembershipPageAutoEnrollSection(PageObject):
    """
    CSV Auto Enroll section of the Membership tab of the Instructor dashboard.
    """
    url = None

    auto_enroll_browse_button_selector = '.auto_enroll_csv .file-browse input.file_field#browseBtn'
    auto_enroll_upload_button_selector = '.auto_enroll_csv button[name="enrollment_signup_button"]'
    NOTIFICATION_ERROR = 'error'
    NOTIFICATION_WARNING = 'warning'
    NOTIFICATION_SUCCESS = 'confirmation'

    def is_browser_on_page(self):
        return self.q(css=self.auto_enroll_browse_button_selector).present

    def is_file_attachment_browse_button_visible(self):
        """
        Returns True if the Auto-Enroll Browse button is present.
        """
        return self.q(css=self.auto_enroll_browse_button_selector).is_present()

    def is_upload_button_visible(self):
        """
        Returns True if the Auto-Enroll Upload button is present.
        """
        return self.q(css=self.auto_enroll_upload_button_selector).is_present()

    def click_upload_file_button(self):
        """
        Clicks the Auto-Enroll Upload Button.
        """
        self.q(css=self.auto_enroll_upload_button_selector).click()

    def is_notification_displayed(self, section_type):
        """
        Valid inputs for section_type: MembershipPageAutoEnrollSection.NOTIFICATION_SUCCESS /
                                       MembershipPageAutoEnrollSection.NOTIFICATION_WARNING /
                                       MembershipPageAutoEnrollSection.NOTIFICATION_ERROR
        Returns True if a {section_type} notification is displayed.
        """
        notification_selector = '.auto_enroll_csv .results .message-%s' % section_type
        self.wait_for_element_presence(notification_selector, "%s Notification" % section_type.title())
        return self.q(css=notification_selector).is_present()

    def first_notification_message(self, section_type):
        """
        Valid inputs for section_type: MembershipPageAutoEnrollSection.NOTIFICATION_WARNING /
                                       MembershipPageAutoEnrollSection.NOTIFICATION_ERROR
        Returns the first message from the list of messages in the {section_type} section.
        """
        error_message_selector = '.auto_enroll_csv .results .message-%s li.summary-item' % section_type
        self.wait_for_element_presence(error_message_selector, "%s message" % section_type.title())
        return self.q(css=error_message_selector).text[0]

    def upload_correct_csv_file(self):
        """
        Selects the correct file and clicks the upload button.
        """
        self._upload_file('auto_reg_enrollment.csv')

    def upload_csv_file_with_errors_warnings(self):
        """
        Selects the file which will generate errors and warnings and clicks the upload button.
        """
        self._upload_file('auto_reg_enrollment_errors_warnings.csv')

    def upload_non_csv_file(self):
        """
        Selects an image file and clicks the upload button.
        """
        self._upload_file('image.jpg')

    def _upload_file(self, filename):
        """
        Helper method to upload a file with registration and enrollment information.
        """
        file_path = InstructorDashboardPage.get_asset_path(filename)
        self.q(css=self.auto_enroll_browse_button_selector).results[0].send_keys(file_path)
        self.click_upload_file_button()


class DataDownloadPage(PageObject):
    """
    Data Download section of the Instructor dashboard.
    """
    url = None

    def is_browser_on_page(self):
        return self.q(css='a[data-section=data_download].active-section').present

    def get_available_reports_for_download(self):
        """
        Returns a list of all the available reports for download.
        """
        reports = self.q(css="#report-downloads-table .file-download-link>a").map(lambda el: el.text)
        return reports.results
