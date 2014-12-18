#-*- coding: utf-8 -*-
"""
Unit tests for video-related REST APIs.
"""
# pylint: disable=attribute-defined-outside-init
import csv
import json
import dateutil.parser
import re
from StringIO import StringIO

from django.conf import settings
from django.test.utils import override_settings
from mock import Mock, patch

from edxval.api import create_profile, create_video, get_video_info

from contentstore.views.videos import KEY_EXPIRATION_IN_SECONDS, VIDEO_ASSET_TYPE
from contentstore.tests.utils import CourseTestCase
from contentstore.utils import reverse_course_url
from xmodule.assetstore import AssetMetadata
from xmodule.modulestore.django import modulestore


class VideoUploadTestMixin(object):
    """
    Test cases for the video upload page
    """
    def get_url_for_course_key(self, course_key):
        """Return video handler URL for the given course"""
        return reverse_course_url(self.VIEW_NAME, course_key)

    def setUp(self):
        super(VideoUploadTestMixin, self).setUp()
        self.url = self.get_url_for_course_key(self.course.id)
        self.test_token = "test_token"
        self.course.video_upload_pipeline = {
            "course_video_upload_token": self.test_token,
        }
        self.save_course()
        self.profiles = [
            {
                "profile_name": "profile1",
                "extension": "mp4",
                "width": 640,
                "height": 480,
            },
            {
                "profile_name": "profile2",
                "extension": "mp4",
                "width": 1920,
                "height": 1080,
            },
        ]
        self.previous_uploads = [
            {
                "edx_video_id": "test1",
                "client_video_id": "test1.mp4",
                "duration": 42.0,
                "status": "transcode_active",
                "encoded_videos": [],
            },
            {
                "edx_video_id": "test2",
                "client_video_id": "test2.mp4",
                "duration": 128.0,
                "status": "file_complete",
                "encoded_videos": [
                    {
                        "profile": "profile1",
                        "url": "http://example.com/profile1/test2.mp4",
                        "file_size": 1600,
                        "bitrate": 100,
                    },
                    {
                        "profile": "profile2",
                        "url": "http://example.com/profile2/test2.mov",
                        "file_size": 16000,
                        "bitrate": 1000,
                    },
                ],
            },
            {
                "edx_video_id": "non-ascii",
                "client_video_id": u"nón-ascii-näme.mp4",
                "duration": 256.0,
                "status": "file_delivered",
                "encoded_videos": [
                    {
                        "profile": "profile1",
                        "url": u"http://example.com/profile1/nón-ascii-näme.mp4",
                        "file_size": 3200,
                        "bitrate": 100,
                    },
                ]
            },
        ]
        for profile in self.profiles:
            create_profile(profile)
        for video in self.previous_uploads:
            create_video(video)
            modulestore().save_asset_metadata(
                AssetMetadata(
                    self.course.id.make_asset_key(VIDEO_ASSET_TYPE, video["edx_video_id"])
                ),
                self.user.id
            )

    def _get_previous_upload(self, edx_video_id):
        return next(
            video
            for video in self.previous_uploads
            if video["edx_video_id"] == edx_video_id
        )

    def test_anon_user(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_put(self):
        response = self.client.put(self.url)
        self.assertEqual(response.status_code, 405)

    def test_invalid_course_key(self):
        response = self.client.get(
            self.get_url_for_course_key("Non/Existent/Course")
        )
        self.assertEqual(response.status_code, 404)

    def test_non_staff_user(self):
        client, __ = self.create_non_staff_authed_user_client()
        response = client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_video_pipeline_not_enabled(self):
        settings.FEATURES["ENABLE_VIDEO_UPLOAD_PIPELINE"] = False
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_video_pipeline_not_configured(self):
        settings.VIDEO_UPLOAD_PIPELINE = None
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_course_not_configured(self):
        self.course.video_upload_pipeline = {}
        self.save_course()
        self.assertEqual(self.client.get(self.url).status_code, 404)


@patch.dict("django.conf.settings.FEATURES", {"ENABLE_VIDEO_UPLOAD_PIPELINE": True})
@override_settings(VIDEO_UPLOAD_PIPELINE={"BUCKET": "test_bucket", "ROOT_PATH": "test_root"})
class VideosHandlerTestCase(VideoUploadTestMixin, CourseTestCase):
    VIEW_NAME = "videos_handler"

    def test_get_json(self):
        response = self.client.get_json(self.url)
        self.assertEqual(response.status_code, 200)
        response_videos = json.loads(response.content)["videos"]
        self.assertEqual(len(response_videos), len(self.previous_uploads))
        for response_video in response_videos:
            original_video = self._get_previous_upload(response_video["edx_video_id"])
            self.assertEqual(
                set(response_video.keys()),
                set(["edx_video_id", "client_video_id", "created", "duration", "status"])
            )
            dateutil.parser.parse(response_video["created"])
            for field in ["edx_video_id", "client_video_id", "duration", "status"]:
                self.assertEqual(response_video[field], original_video[field])

    def test_get_html(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertRegexpMatches(response["Content-Type"], "^text/html(;.*)?$")
        # Crude check for presence of data in returned HTML
        for video in self.previous_uploads:
            self.assertIn(video["edx_video_id"], response.content)

    def test_post_non_json(self):
        response = self.client.post(self.url, {"files": []})
        self.assertEqual(response.status_code, 400)

    def test_post_malformed_json(self):
        response = self.client.post(self.url, "{", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_post_invalid_json(self):
        def assert_bad(content):
            """Make request with content and assert that response is 400"""
            response = self.client.post(
                self.url,
                json.dumps(content),
                content_type="application/json"
            )
            self.assertEqual(response.status_code, 400)

        # Top level missing files key
        assert_bad({})

        # Entry missing file_name
        assert_bad({"files": [{"content_type": "video/mp4"}]})

        # Entry missing content_type
        assert_bad({"files": [{"file_name": "test.mp4"}]})

    @override_settings(AWS_ACCESS_KEY_ID="test_key_id", AWS_SECRET_ACCESS_KEY="test_secret")
    @patch("boto.s3.key.Key")
    @patch("boto.s3.connection.S3Connection")
    def test_post_success(self, mock_conn, mock_key):
        files = [
            {
                "file_name": "first.mp4",
                "content_type": "video/mp4",
            },
            {
                "file_name": "second.webm",
                "content_type": "video/webm",
            },
            {
                "file_name": "third.mov",
                "content_type": "video/quicktime",
            },
            {
                "file_name": "fourth.mp4",
                "content_type": "video/mp4",
            },
        ]

        bucket = Mock()
        mock_conn.return_value = Mock(get_bucket=Mock(return_value=bucket))
        mock_key_instances = [
            Mock(
                generate_url=Mock(
                    return_value="http://example.com/url_{}".format(file_info["file_name"])
                )
            )
            for file_info in files
        ]
        # If extra calls are made, return a dummy
        mock_key.side_effect = mock_key_instances + [Mock()]

        response = self.client.post(
            self.url,
            json.dumps({"files": files}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        response_obj = json.loads(response.content)

        mock_conn.assert_called_once_with(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_ACCESS_KEY)
        self.assertEqual(len(response_obj["files"]), len(files))
        self.assertEqual(mock_key.call_count, len(files))
        for i, file_info in enumerate(files):
            # Ensure Key was set up correctly and extract id
            key_call_args, __ = mock_key.call_args_list[i]
            self.assertEqual(key_call_args[0], bucket)
            path_match = re.match(
                (
                    settings.VIDEO_UPLOAD_PIPELINE["ROOT_PATH"] +
                    "/([a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12})$"
                ),
                key_call_args[1]
            )
            self.assertIsNotNone(path_match)
            video_id = path_match.group(1)
            mock_key_instance = mock_key_instances[i]
            mock_key_instance.set_metadata.assert_any_call(
                "course_video_upload_token",
                self.test_token
            )
            mock_key_instance.set_metadata.assert_any_call(
                "client_video_id",
                file_info["file_name"]
            )
            mock_key_instance.set_metadata.assert_any_call("course_key", unicode(self.course.id))
            mock_key_instance.generate_url.assert_called_once_with(
                KEY_EXPIRATION_IN_SECONDS,
                "PUT",
                headers={"Content-Type": file_info["content_type"]}
            )

            # Ensure asset store was updated
            self.assertIsNotNone(
                modulestore().find_asset_metadata(
                    self.course.id.make_asset_key(VIDEO_ASSET_TYPE, video_id)
                )
            )

            # Ensure VAL was updated
            val_info = get_video_info(video_id)
            self.assertEqual(val_info["status"], "upload")
            self.assertEqual(val_info["client_video_id"], file_info["file_name"])
            self.assertEqual(val_info["status"], "upload")
            self.assertEqual(val_info["duration"], 0)

            # Ensure response is correct
            response_file = response_obj["files"][i]
            self.assertEqual(response_file["file_name"], file_info["file_name"])
            self.assertEqual(response_file["upload_url"], mock_key_instance.generate_url())


@patch.dict("django.conf.settings.FEATURES", {"ENABLE_VIDEO_UPLOAD_PIPELINE": True})
@override_settings(VIDEO_UPLOAD_PIPELINE={"BUCKET": "test_bucket", "ROOT_PATH": "test_root"})
class VideoUrlsCsvTestCase(VideoUploadTestMixin, CourseTestCase):
    VIEW_NAME = "videos_url_list"

    def test_get_csv(self):
        response = self.client.get(self.url, HTTP_ACCEPT="text/csv")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="{course}_video_urls.csv"'.format(course=self.course.id.course)
        )
        response_reader = StringIO(response.content)
        reader = csv.DictReader(response_reader, dialect=csv.excel)
        self.assertEqual(
            reader.fieldnames,
            ["Name", "Duration", "Date Added", "Video ID", "profile1 URL", "profile2 URL"]
        )
        count = 0
        for row in reader:
            count += 1
            response_video = {
                key.decode("utf-8"): value.decode("utf-8") for key, value in row.items()
            }
            original_video = self._get_previous_upload(response_video["Video ID"])
            self.assertEqual(response_video["Name"], original_video["client_video_id"])
            self.assertEqual(response_video["Video ID"], original_video["edx_video_id"])
            for profile in self.profiles:
                profile_name = profile["profile_name"]
                response_profile_url = response_video[
                    "{profile_name} URL".format(profile_name=profile_name)
                ]
                original_encoded_for_profile = next(
                    (
                        original_encoded
                        for original_encoded in original_video["encoded_videos"]
                        if original_encoded["profile"] == profile["profile_name"]
                    ),
                    None
                )
                if original_encoded_for_profile:
                    self.assertEqual(response_profile_url, original_encoded_for_profile["url"])
                else:
                    self.assertEqual(response_profile_url, "")
        self.assertEqual(count, len(self.previous_uploads))
