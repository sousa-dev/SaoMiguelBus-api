from unittest.mock import patch
from django.test import TestCase
from app.utils import get_media

class GetMediaTests(TestCase):

	@patch('app.utils.os.path')
	def test_file_does_not_exist(self, mock_path):
		mock_path.exists.return_value = False
		
		response = get_media('nonexistent/file')
		
		self.assertEqual(response.status_code, 404)
		self.assertJSONEqual(str(response.content, encoding='utf8'), {'error': 'File not found'})