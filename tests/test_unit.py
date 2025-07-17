import pytest
from unittest.mock import patch, MagicMock
import os
import sys
import shutil
import subprocess
import requests
import functools
import tempfile

from ripzilla.utils import check_media_tools_installed, has_audio_stream, detect_best_hwaccel, _check_disk_space, download_video, _get_hwaccel_for_extraction
from ripzilla.extractors import _build_ffmpeg_cmd, _run_ffmpeg, try_stream_extract, try_local_extract, fallback_download_extract
from ripzilla.exceptions import FFprobeError, RipzillaTimeoutError, DiskSpaceError, NetworkError, FFmpegError

@pytest.fixture(autouse=True)
def clear_lru_cache():
    detect_best_hwaccel.cache_clear()

# --- Unit Tests for ripzilla.utils ---

@patch('shutil.which')
def test_check_media_tools_installed_success(mock_which):
    mock_which.side_effect = lambda x: f'/usr/bin/{x}'
    assert check_media_tools_installed() is True
    mock_which.assert_any_call('ffmpeg')
    mock_which.assert_any_call('ffprobe')

@patch('shutil.which')
def test_check_media_tools_installed_ffmpeg_not_found(mock_which):
    mock_which.side_effect = lambda x: None if x == 'ffmpeg' else f'/usr/bin/{x}'
    with pytest.raises(FileNotFoundError, match='ffmpeg executable not found'):
        check_media_tools_installed()

@patch('shutil.which')
def test_check_media_tools_installed_ffprobe_not_found(mock_which):
    mock_which.side_effect = lambda x: None if x == 'ffprobe' else f'/usr/bin/{x}'
    with pytest.raises(FileNotFoundError, match='ffprobe executable not found'):
        check_media_tools_installed()

@patch('subprocess.run')
def test_has_audio_stream_success(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout='Stream #0:0: Audio: aac', stderr='')
    assert has_audio_stream('dummy_input.mp4') is True
    mock_run.assert_called_once()

@patch('subprocess.run')
def test_has_audio_stream_no_audio(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout='Stream #0:0: Video: h264', stderr='')
    assert has_audio_stream('dummy_input.mp4') is False
    mock_run.assert_called_once()

@patch('subprocess.run')
def test_has_audio_stream_ffprobe_error(mock_run):
    mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='Error message')
    with pytest.raises(FFprobeError, match='ffprobe failed'):
        has_audio_stream('dummy_input.mp4')
    mock_run.assert_called_once()

@patch('subprocess.run')
def test_has_audio_stream_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd='ffprobe', timeout=10)
    with pytest.raises(RipzillaTimeoutError, match='ffprobe command timed out'):
        has_audio_stream('dummy_input.mp4')
    mock_run.assert_called_once()

@patch('subprocess.run')
def test_detect_best_hwaccel_macos_videotoolbox(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout='Hardware acceleration methods:\nvideotoolbox\nother_accel', stderr='')
    assert detect_best_hwaccel() == 'videotoolbox'

@patch('subprocess.run')
def test_detect_best_hwaccel_linux_cuda(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout='Hardware acceleration methods:\ncuda\nvdpau', stderr='')
    assert detect_best_hwaccel() == 'cuda'

@patch('subprocess.run')
def test_detect_best_hwaccel_no_preferred(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout='''Hardware acceleration methods:\nvaapi\nopencl''', stderr='')
    assert detect_best_hwaccel() is None

@patch('subprocess.run')
def test_detect_best_hwaccel_ffmpeg_not_found(mock_run):
    mock_run.side_effect = FileNotFoundError
    assert detect_best_hwaccel() is None

@patch('shutil.disk_usage')
def test_check_disk_space_sufficient(mock_disk_usage):
    mock_disk_usage.return_value = MagicMock(free=2 * (1024**3)) # 2 GB free
    assert _check_disk_space('/tmp', 1.0) is True

@patch('shutil.disk_usage')
def test_check_disk_space_insufficient(mock_disk_usage):
    mock_disk_usage.return_value = MagicMock(free=0.5 * (1024**3)) # 0.5 GB free
    with pytest.raises(DiskSpaceError, match='Insufficient disk space'):
        _check_disk_space('/tmp', 1.0)

@patch('ripzilla.utils.requests.get')
def test_download_video_success(mock_get):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.iter_content.return_value = [b'chunk1', b'chunk2']
    mock_get.return_value.__enter__.return_value = mock_response

    mock_file = MagicMock()
    with patch('builtins.open', return_value=mock_file):
        download_video('http://example.com/video.mp4', 'output.mp4')
        mock_get.assert_called_once_with('http://example.com/video.mp4', stream=True, timeout=60)
        mock_file.__enter__.return_value.write.assert_any_call(b'chunk1')
        mock_file.__enter__.return_value.write.assert_any_call(b'chunk2')

@patch('ripzilla.utils.requests.get')
def test_download_video_network_error(mock_get):
    mock_get.side_effect = requests.exceptions.RequestException('Network issue')
    with pytest.raises(NetworkError, match='Failed to download video'):
        download_video('http://example.com/video.mp4', 'output.mp4')

@patch('ripzilla.utils.requests.get')
def test_download_video_timeout(mock_get):
    mock_get.side_effect = requests.exceptions.Timeout('Connection timed out')
    with pytest.raises(RipzillaTimeoutError, match='Connection timed out'):
        download_video('http://example.com/video.mp4', 'output.mp4')

@patch('ripzilla.utils.detect_best_hwaccel')
def test_get_hwaccel_for_extraction_auto_detected(mock_detect):
    mock_detect.return_value = 'videotoolbox'
    assert _get_hwaccel_for_extraction('auto') == 'videotoolbox'

@patch('ripzilla.utils.detect_best_hwaccel')
def test_get_hwaccel_for_extraction_auto_not_detected(mock_detect):
    mock_detect.return_value = None
    assert _get_hwaccel_for_extraction('auto') is None

@patch('ripzilla.utils.detect_best_hwaccel')
def test_get_hwaccel_for_extraction_gpu_detected(mock_detect):
    mock_detect.return_value = 'cuda'
    assert _get_hwaccel_for_extraction('gpu') == 'cuda'

@patch('ripzilla.utils.detect_best_hwaccel')
def test_get_hwaccel_for_extraction_gpu_not_detected(mock_detect):
    mock_detect.return_value = None
    with patch('ripzilla.utils.logger.warning') as mock_warn:
        assert _get_hwaccel_for_extraction('gpu') is None
        mock_warn.assert_called_once_with('GPU acceleration requested, but no compatible method detected. Using CPU.')

@patch('ripzilla.utils.detect_best_hwaccel')
def test_get_hwaccel_for_extraction_cpu(mock_detect):
    assert _get_hwaccel_for_extraction('cpu') is None
    mock_detect.assert_not_called()

# --- Unit Tests for ripzilla.extractors ---

def test_build_ffmpeg_cmd_raw_quality():
    cmd = _build_ffmpeg_cmd('input.mp4', 'output.aac', 'raw', None)
    assert cmd == ['ffmpeg', '-y', '-i', 'input.mp4', '-vn', '-acodec', 'copy', 'output.aac']

def test_build_ffmpeg_cmd_high_quality_with_hwaccel():
    cmd = _build_ffmpeg_cmd('input.mp4', 'output.aac', 'high', 'videotoolbox')
    assert cmd == ['ffmpeg', '-y', '-hwaccel', 'videotoolbox', '-i', 'input.mp4', '-vn', '-acodec', 'aac', '-b:a', '192k', 'output.aac']

def test_build_ffmpeg_cmd_low_quality():
    cmd = _build_ffmpeg_cmd('input.mp4', 'output.opus', 'low', None)
    expected_cmd_parts = ['ffmpeg', '-y', '-i', 'input.mp4', '-vn', '-acodec', 'libopus', '-b:a', '64k', '-ar', '16000', '-ac', '1', '-af', 'highpass=f=200', 'output.opus']
    assert cmd == expected_cmd_parts

def test_build_ffmpeg_cmd_invalid_quality():
    with pytest.raises(ValueError, match='Invalid audio quality preset'):
        _build_ffmpeg_cmd('input.mp4', 'output.aac', 'invalid', None)

@patch('subprocess.run')
@patch('os.path.exists', return_value=True)
@patch('os.path.getsize', return_value=100)
def test_run_ffmpeg_success(mock_getsize, mock_exists, mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout='ffmpeg output', stderr='')
    _run_ffmpeg(['ffmpeg', '-i', 'input', 'output'], 'output.aac')
    mock_run.assert_called_once()
    mock_exists.assert_called_once_with('output.aac')
    mock_getsize.assert_called_once_with('output.aac')

@patch('subprocess.run')
@patch('os.path.exists', return_value=True)
@patch('os.remove')
def test_run_ffmpeg_failure_return_code(mock_remove, mock_exists, mock_run):
    mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='ffmpeg error')
    with pytest.raises(FFmpegError, match='FFmpeg command failed'):
        _run_ffmpeg(['ffmpeg', '-i', 'input', 'output'], 'output.aac')
    mock_run.assert_called_once()
    mock_remove.assert_called_once_with('output.aac')

@patch('subprocess.run')
@patch('os.path.exists', side_effect=[True, False]) # First exists check passes, second fails
@patch('os.path.getsize', return_value=0)
def test_run_ffmpeg_output_file_missing_or_empty(mock_getsize, mock_exists, mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout='ffmpeg output', stderr='')
    with pytest.raises(FFmpegError, match='output file .* is missing or empty'):
        _run_ffmpeg(['ffmpeg', '-i', 'input', 'output'], 'output.aac')
    mock_run.assert_called_once()
    assert mock_exists.call_count == 1 # Corrected assertion
    mock_getsize.assert_called_once_with('output.aac')

@patch('subprocess.run')
def test_run_ffmpeg_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd='ffmpeg', timeout=600)
    with pytest.raises(RipzillaTimeoutError, match=r'FFmpeg command timed out after 600 seconds: ffmpeg -i input output'): # Adjusted regex
        _run_ffmpeg(['ffmpeg', '-i', 'input', 'output'], 'output.aac')
    mock_run.assert_called_once()

@patch('ripzilla.extractors._get_hwaccel_for_extraction', return_value=None)
@patch('ripzilla.extractors._run_ffmpeg')
def test_try_stream_extract_success(mock_run_ffmpeg, mock_get_hwaccel):
    try_stream_extract('http://example.com/video.mp4', 'output.aac')
    mock_run_ffmpeg.assert_called_once()
    mock_get_hwaccel.assert_called_once_with('auto')

@patch('ripzilla.extractors._get_hwaccel_for_extraction', return_value=None)
@patch('ripzilla.extractors._run_ffmpeg', side_effect=FFmpegError('test error'))
def test_try_stream_extract_failure_retries(mock_run_ffmpeg, mock_get_hwaccel):
    with pytest.raises(FFmpegError):
        try_stream_extract('http://example.com/video.mp4', 'output.aac')
    assert mock_run_ffmpeg.call_count == 3 # Retries 3 times

@patch('ripzilla.extractors._get_hwaccel_for_extraction', return_value='videotoolbox')
@patch('os.path.exists', return_value=True)
@patch('ripzilla.extractors._run_ffmpeg')
def test_try_local_extract_success(mock_run_ffmpeg, mock_exists, mock_get_hwaccel):
    try_local_extract('/path/to/local.mp4', 'output.aac')
    mock_run_ffmpeg.assert_called_once()
    mock_exists.assert_called_once_with('/path/to/local.mp4')
    mock_get_hwaccel.assert_called_once_with('auto')

@patch('ripzilla.extractors._get_hwaccel_for_extraction', return_value=None)
@patch('os.path.exists', return_value=True)
@patch('ripzilla.extractors._run_ffmpeg', side_effect=FFmpegError('test error'))
def test_try_local_extract_failure_retries(mock_run_ffmpeg, mock_exists, mock_get_hwaccel):
    with pytest.raises(FFmpegError):
        try_local_extract('/path/to/local.mp4', 'output.aac')
    assert mock_run_ffmpeg.call_count == 3 # Retries 3 times

@patch('os.unlink')
@patch('tempfile.NamedTemporaryFile')
@patch('ripzilla.utils._check_disk_space')
@patch('ripzilla.extractors.try_local_extract')
@patch('ripzilla.utils.requests.get')
def test_fallback_download_extract_success(mock_get, mock_try_local_extract, mock_check_disk_space, mock_tempfile, mock_unlink):
    mock_temp_file_obj = MagicMock()
    mock_temp_file_obj.name = '/tmp/temp_video.mp4'
    mock_tempfile.return_value.__enter__.return_value = mock_temp_file_obj

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.iter_content.return_value = [b'chunk1', b'chunk2']
    mock_get.return_value.__enter__.return_value = mock_response

    fallback_download_extract('http://example.com/video.mp4', 'output.aac', min_disk_space_gb=0.5)

    mock_check_disk_space.assert_called_once_with(os.path.normpath(tempfile.gettempdir()), min_required_gb=0.5)
    mock_get.assert_called_once_with('http://example.com/video.mp4', stream=True, timeout=60)
    mock_try_local_extract.assert_called_once_with('/tmp/temp_video.mp4', 'output.aac', ffmpeg_timeout=600, hwaccel_mode='auto', quality='raw')
    mock_unlink.assert_called_once_with('/tmp/temp_video.mp4')

@patch('os.unlink')
@patch('tempfile.NamedTemporaryFile')
@patch('ripzilla.utils._check_disk_space')
@patch('ripzilla.utils.requests.get', side_effect=requests.exceptions.RequestException('Download failed'))
def test_fallback_download_extract_download_failure(mock_get, mock_check_disk_space, mock_tempfile, mock_unlink):
    mock_temp_file_obj = MagicMock()
    mock_temp_file_obj.name = '/tmp/temp_video.mp4'
    mock_tempfile.return_value.__enter__.return_value = mock_temp_file_obj

    with pytest.raises(NetworkError):
        fallback_download_extract('http://example.com/video.mp4', 'output.aac')

    mock_unlink.assert_called_once()

@patch('os.unlink')
@patch('tempfile.NamedTemporaryFile')
@patch('ripzilla.utils.requests.get', side_effect=requests.exceptions.RequestException('Download failed'))
@patch('ripzilla.utils._check_disk_space', side_effect=DiskSpaceError('No space'))
def test_fallback_download_extract_disk_space_failure(mock_check_disk_space, mock_get, mock_tempfile, mock_unlink):
    mock_temp_file_obj = MagicMock()
    mock_temp_file_obj.name = '/tmp/temp_video.mp4'
    mock_tempfile.return_value.__enter__.return_value = mock_temp_file_obj

    with pytest.raises(DiskSpaceError):
        fallback_download_extract('http://example.com/video.mp4', 'output.aac')

    mock_unlink.assert_called_once()

@patch('os.unlink')
@patch('tempfile.NamedTemporaryFile')
@patch('ripzilla.utils._check_disk_space')
@patch('ripzilla.utils.requests.get')
@patch('ripzilla.extractors.try_local_extract', side_effect=FFmpegError('Local extract failed'))
def test_fallback_download_extract_local_extract_failure(mock_try_local_extract, mock_get, mock_check_disk_space, mock_tempfile, mock_unlink):
    mock_temp_file_obj = MagicMock()
    mock_temp_file_obj.name = '/tmp/temp_video.mp4'
    mock_tempfile.return_value.__enter__.return_value = mock_temp_file_obj

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.iter_content.return_value = [b'chunk1', b'chunk2']
    mock_get.return_value.__enter__.return_value = mock_response

    with pytest.raises(FFmpegError):
        fallback_download_extract('http://example.com/video.mp4', 'output.aac')

    mock_try_local_extract.assert_called_once()
    mock_unlink.assert_called_once()