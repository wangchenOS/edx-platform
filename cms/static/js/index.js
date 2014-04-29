define(["domReady", "jquery", "underscore", "js/utils/cancel_on_escape", "js/views/utils/create_course_utils",
    "js/views/utils/view_utils", "js/views/license-selector"],
    function (domReady, $, _, CancelOnEscape, CreateCourseUtilsFactory, ViewUtils, LicenseSelector) {
        var CreateCourseUtils = CreateCourseUtilsFactory({
            name: '.new-course-name',
            org: '.new-course-org',
            number: '.new-course-number',
            run: '.new-course-run',
            save: '.new-course-save',
            errorWrapper: '.wrap-error',
            errorMessage: '#course_creation_error',
            tipError: 'span.tip-error',
            error: '.error',
            allowUnicode: '.allow-unicode-course-id'
        }, {
            shown: 'is-shown',
            showing: 'is-showing',
            hiding: 'is-hiding',
            disabled: 'is-disabled',
            error: 'error'
        });

        var saveNewCourse = function (e) {
            e.preventDefault();

            if (CreateCourseUtils.hasInvalidRequiredFields()) {
                return;
            }

            var $newCourseForm = $(this).closest('#create-course-form');
            var display_name = $newCourseForm.find('.new-course-name').val();
            var org = $newCourseForm.find('.new-course-org').val();
            var number = $newCourseForm.find('.new-course-number').val();
            var run = $newCourseForm.find('.new-course-run').val();
            var license = {};
            if(licenseSelector){
                // When the license selector is present (CREATIVE_COMMONS_LICENSING feature flag is set to true)
                // we will take the value of the selector into account.
                license = licenseSelector.model.toJSON();
            }

            course_info = {
                org: org,
                number: number,
                display_name: display_name,
                run: run,
                license: license
            };

            analytics.track('Created a Course', course_info);
            CreateCourseUtils.createCourse(course_info, function (errorMessage) {
                $('.wrap-error').addClass('is-shown');
                $('#course_creation_error').html('<p>' + errorMessage + '</p>');
                $('.new-course-save').addClass('is-disabled').attr('aria-disabled', true);
            });
        };

        var cancelNewCourse = function (e) {
            e.preventDefault();
            $('.new-course-button').removeClass('is-disabled').attr('aria-disabled', false);
            $('.wrapper-create-course').removeClass('is-shown');
            // Clear out existing fields and errors
            _.each(
                ['.new-course-name', '.new-course-org', '.new-course-number', '.new-course-run', '#create-course-form .license'],
                function (field) {
                    $(field).val('');
                }
            );
            $('#course_creation_error').html('');
            $('.wrap-error').removeClass('is-shown');
            $('.new-course-save').off('click');
        };

        var addNewCourse = function (e) {
            e.preventDefault();
            $('.new-course-button').addClass('is-disabled').attr('aria-disabled', true);
            $('.new-course-save').addClass('is-disabled').attr('aria-disabled', true);
            var $newCourse = $('.wrapper-create-course').addClass('is-shown');
            var $cancelButton = $newCourse.find('.new-course-cancel');
            var $courseName = $('.new-course-name');
            $courseName.focus().select();
            $('.new-course-save').on('click', saveNewCourse);
            $cancelButton.bind('click', cancelNewCourse);
            CancelOnEscape($cancelButton);

            CreateCourseUtils.configureHandlers();
        };

        // Keep track of the license selector in the scope of this file
        var licenseSelector;

        var onReady = function () {
            var fieldCourseLicense;
            $('.new-course-button').bind('click', addNewCourse);
            $('.dismiss-button').bind('click', ViewUtils.deleteNotificationHandler(function () {
                ViewUtils.reload();
            }));
            $('.action-reload').bind('click', ViewUtils.reload);

            // When the user is not allowed to set the license on a course, the
            // field-course-license element will not be found.
            fieldCourseLicense = document.getElementById("field-course-license");
            if(fieldCourseLicense){
                // Licencing in new course form
                licenseSelector = new LicenseSelector({el: fieldCourseLicense});
            }
        };

        domReady(onReady);

        return {
            onReady: onReady
        };
    });
