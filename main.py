from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import tempfile
import json
from urllib.parse import urlparse
import re
import threading
import time
import uuid
from datetime import datetime
import zipfile
import io
import ffmpeg
import subprocess
import shutil
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Configure temp directory
TEMP_DIR = tempfile.mkdtemp()
DOWNLOAD_TASKS = {}  # Store download progress

class FFmpegProcessor:
    """Enhanced FFmpeg processing class"""
    
    def __init__(self):
        self.check_ffmpeg_availability()
    
    def check_ffmpeg_availability(self):
        """Check if FFmpeg is available"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.ffmpeg_available = True
                print("FFmpeg is available")
            else:
                self.ffmpeg_available = False
                print("FFmpeg not found")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self.ffmpeg_available = False
            print("FFmpeg not available")
    
    def convert_video(self, input_path, output_format='mp4', quality='medium', resolution=None):
        """Convert video to specified format and quality"""
        if not self.ffmpeg_available:
            raise Exception("FFmpeg is not available")
        
        output_path = self._get_output_path(input_path, output_format)
        
        # Build FFmpeg stream
        stream = ffmpeg.input(input_path)
        
        # Quality settings
        video_opts = {}
        audio_opts = {}
        
        if quality == 'high':
            video_opts['crf'] = 18
            audio_opts['audio_bitrate'] = '320k'
        elif quality == 'medium':
            video_opts['crf'] = 23
            audio_opts['audio_bitrate'] = '192k'
        elif quality == 'low':
            video_opts['crf'] = 28
            audio_opts['audio_bitrate'] = '128k'
        
        # Resolution scaling
        if resolution:
            if resolution == '720p':
                video_opts['vf'] = 'scale=-2:720'
            elif resolution == '1080p':
                video_opts['vf'] = 'scale=-2:1080'
            elif resolution == '480p':
                video_opts['vf'] = 'scale=-2:480'
        
        # Apply settings and run conversion
        stream = ffmpeg.output(stream, output_path, **video_opts, **audio_opts)
        ffmpeg.run(stream, overwrite_output=True, quiet=True)
        
        return output_path
    
    def extract_audio(self, input_path, output_format='mp3', quality='192k'):
        """Extract audio from video"""
        if not self.ffmpeg_available:
            raise Exception("FFmpeg is not available")
        
        output_path = self._get_output_path(input_path, output_format)
        
        stream = ffmpeg.input(input_path)
        stream = ffmpeg.output(stream, output_path, acodec='libmp3lame', audio_bitrate=quality)
        ffmpeg.run(stream, overwrite_output=True, quiet=True)
        
        return output_path
    
    def compress_video(self, input_path, compression_level='medium'):
        """Compress video file"""
        if not self.ffmpeg_available:
            raise Exception("FFmpeg is not available")
        
        output_path = self._get_output_path(input_path, 'mp4', suffix='_compressed')
        
        # Compression settings
        crf_values = {'low': 35, 'medium': 28, 'high': 23}
        crf = crf_values.get(compression_level, 28)
        
        stream = ffmpeg.input(input_path)
        stream = ffmpeg.output(stream, output_path, crf=crf, preset='medium')
        ffmpeg.run(stream, overwrite_output=True, quiet=True)
        
        return output_path
    
    def trim_video(self, input_path, start_time, duration):
        """Trim video to specified duration"""
        if not self.ffmpeg_available:
            raise Exception("FFmpeg is not available")
        
        output_path = self._get_output_path(input_path, 'mp4', suffix='_trimmed')
        
        stream = ffmpeg.input(input_path, ss=start_time, t=duration)
        stream = ffmpeg.output(stream, output_path, c='copy')
        ffmpeg.run(stream, overwrite_output=True, quiet=True)
        
        return output_path
    
    def merge_videos(self, video_paths, output_format='mp4'):
        """Merge multiple videos into one"""
        if not self.ffmpeg_available:
            raise Exception("FFmpeg is not available")
        
        if len(video_paths) < 2:
            raise Exception("At least 2 videos required for merging")
        
        output_path = os.path.join(TEMP_DIR, f'merged_video_{int(time.time())}.{output_format}')
        
        # Create input streams
        inputs = [ffmpeg.input(path) for path in video_paths]
        
        # Concatenate videos
        stream = ffmpeg.concat(*inputs, v=1, a=1)
        stream = ffmpeg.output(stream, output_path)
        ffmpeg.run(stream, overwrite_output=True, quiet=True)
        
        return output_path
    
    def add_watermark(self, input_path, watermark_text, position='bottom-right'):
        """Add text watermark to video"""
        if not self.ffmpeg_available:
            raise Exception("FFmpeg is not available")
        
        output_path = self._get_output_path(input_path, 'mp4', suffix='_watermarked')
        
        # Position mapping
        positions = {
            'top-left': 'x=10:y=10',
            'top-right': 'x=w-tw-10:y=10',
            'bottom-left': 'x=10:y=h-th-10',
            'bottom-right': 'x=w-tw-10:y=h-th-10',
            'center': 'x=(w-tw)/2:y=(h-th)/2'
        }
        
        position_coords = positions.get(position, positions['bottom-right'])
        
        stream = ffmpeg.input(input_path)
        stream = ffmpeg.output(
            stream, output_path,
            vf=f"drawtext=text='{watermark_text}':fontcolor=white:fontsize=24:{position_coords}"
        )
        ffmpeg.run(stream, overwrite_output=True, quiet=True)
        
        return output_path
    
    def get_video_info(self, input_path):
        """Get detailed video information using FFmpeg"""
        if not self.ffmpeg_available:
            return None
        
        try:
            probe = ffmpeg.probe(input_path)
            video_info = {}
            
            # General info
            format_info = probe.get('format', {})
            video_info['duration'] = float(format_info.get('duration', 0))
            video_info['size'] = int(format_info.get('size', 0))
            video_info['bit_rate'] = int(format_info.get('bit_rate', 0))
            
            # Video stream info
            video_streams = [s for s in probe['streams'] if s['codec_type'] == 'video']
            if video_streams:
                v_stream = video_streams[0]
                video_info['width'] = v_stream.get('width')
                video_info['height'] = v_stream.get('height')
                video_info['fps'] = eval(v_stream.get('r_frame_rate', '0/1'))
                video_info['video_codec'] = v_stream.get('codec_name')
            
            # Audio stream info
            audio_streams = [s for s in probe['streams'] if s['codec_type'] == 'audio']
            if audio_streams:
                a_stream = audio_streams[0]
                video_info['audio_codec'] = a_stream.get('codec_name')
                video_info['sample_rate'] = a_stream.get('sample_rate')
                video_info['channels'] = a_stream.get('channels')
            
            return video_info
        except Exception as e:
            print(f"Error getting video info: {e}")
            return None
    
    def _get_output_path(self, input_path, output_format, suffix='_processed'):
        """Generate output file path"""
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        return os.path.join(TEMP_DIR, f'{base_name}{suffix}.{output_format}')

class AdvancedSocialMediaDownloader:
    def __init__(self):
        self.ffmpeg_processor = FFmpegProcessor()
        self.supported_platforms = {
            'youtube.com': 'YouTube',
            'youtu.be': 'YouTube',
            'twitter.com': 'Twitter',
            'x.com': 'Twitter',
            'instagram.com': 'Instagram',
            'tiktok.com': 'TikTok',
            'facebook.com': 'Facebook',
            'vimeo.com': 'Vimeo',
            'dailymotion.com': 'Dailymotion',
            'twitch.tv': 'Twitch',
            'reddit.com': 'Reddit',
            'soundcloud.com': 'SoundCloud'
        }
        
        self.format_presets = {
            'best_video': 'best[ext=mp4]/best',
            'best_audio': 'bestaudio[ext=m4a]/bestaudio',
            'worst_video': 'worst[ext=mp4]/worst',
            'hd_720p': 'best[height<=720][ext=mp4]',
            'hd_1080p': 'best[height<=1080][ext=mp4]',
            '4k': 'best[height<=2160][ext=mp4]',
            'audio_only': 'bestaudio/best',
            'video_only': 'bestvideo[ext=mp4]'
        }
        
        # Enhanced format presets with FFmpeg processing
        self.processing_presets = {
            'compress_high': {'action': 'compress', 'level': 'high'},
            'compress_medium': {'action': 'compress', 'level': 'medium'},
            'compress_low': {'action': 'compress', 'level': 'low'},
            'extract_audio_mp3': {'action': 'extract_audio', 'format': 'mp3'},
            'extract_audio_aac': {'action': 'extract_audio', 'format': 'aac'},
            'convert_to_mp4': {'action': 'convert', 'format': 'mp4'},
            'convert_to_webm': {'action': 'convert', 'format': 'webm'},
            'scale_720p': {'action': 'convert', 'format': 'mp4', 'resolution': '720p'},
            'scale_1080p': {'action': 'convert', 'format': 'mp4', 'resolution': '1080p'}
        }
    
    def get_platform(self, url):
        domain = urlparse(url).netloc.lower()
        for platform_domain, platform_name in self.supported_platforms.items():
            if platform_domain in domain:
                return platform_name
        return 'Unknown'
    
    def validate_url(self, url):
        """Enhanced URL validation"""
        if not url or not isinstance(url, str):
            return False, "URL is required"
        
        url_pattern = re.compile(
            r'^https?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?'
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        if not url_pattern.match(url):
            return False, "Invalid URL format"
        
        # Check if platform is supported
        platform = self.get_platform(url)
        if platform == 'Unknown':
            return True, "URL appears valid but platform may not be fully supported"
        
        return True, "Valid URL"
    
    def get_video_info(self, url, include_formats=True):
        """Enhanced video information extraction"""
        ydl_opts = {
            'quiet': True,
            'extract_flat': False,
            'no_warnings': True,
            'writesubtitles': False,
            'writeautomaticsub': False
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Extract comprehensive information
                video_info = {
                    'id': info.get('id', ''),
                    'title': info.get('title', 'Unknown'),
                    'description': info.get('description', '')[:500] + '...' if info.get('description') and len(info.get('description')) > 500 else info.get('description', ''),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'uploader_id': info.get('uploader_id', ''),
                    'upload_date': info.get('upload_date', ''),
                    'view_count': info.get('view_count', 0),
                    'like_count': info.get('like_count', 0),
                    'comment_count': info.get('comment_count', 0),
                    'thumbnail': info.get('thumbnail', ''),
                    'platform': self.get_platform(url),
                    'webpage_url': info.get('webpage_url', url),
                    'tags': info.get('tags', [])[:10] if info.get('tags') else [],
                    'categories': info.get('categories', []),
                    'subtitles': list(info.get('subtitles', {}).keys()),
                    'automatic_captions': list(info.get('automatic_captions', {}).keys()),
                    'ffmpeg_available': self.ffmpeg_processor.ffmpeg_available
                }
                
                if include_formats:
                    video_info['formats'] = self._get_available_formats(info)
                    video_info['format_presets'] = self.format_presets
                    video_info['processing_presets'] = self.processing_presets
                
                return video_info
        except Exception as e:
            raise Exception(f"Error extracting video info: {str(e)}")
    
    def _get_available_formats(self, info):
        """Enhanced format extraction with categorization"""
        formats = {
            'video': [],
            'audio': [],
            'combined': []
        }
        
        if 'formats' in info:
            for fmt in info['formats']:
                format_info = {
                    'format_id': fmt.get('format_id'),
                    'ext': fmt.get('ext'),
                    'quality': fmt.get('height', fmt.get('quality', 'unknown')),
                    'filesize': fmt.get('filesize', 0),
                    'filesize_approx': fmt.get('filesize_approx', 0),
                    'fps': fmt.get('fps'),
                    'vcodec': fmt.get('vcodec', 'none'),
                    'acodec': fmt.get('acodec', 'none'),
                    'abr': fmt.get('abr'),  # Audio bitrate
                    'vbr': fmt.get('vbr'),  # Video bitrate
                    'format_note': fmt.get('format_note', ''),
                    'resolution': fmt.get('resolution', 'unknown')
                }
                
                # Categorize formats
                if fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none':
                    formats['combined'].append(format_info)
                elif fmt.get('vcodec') != 'none':
                    formats['video'].append(format_info)
                elif fmt.get('acodec') != 'none':
                    formats['audio'].append(format_info)
        
        # Limit results and sort by quality
        for category in formats:
            formats[category] = sorted(formats[category][:15], 
                                     key=lambda x: x.get('quality', 0) if isinstance(x.get('quality'), int) else 0, 
                                     reverse=True)
        
        return formats
    
    def download_video(self, url, format_selector='best', task_id=None, download_subtitles=False, post_process=None):
        """Enhanced download with FFmpeg post-processing"""
        if task_id:
            DOWNLOAD_TASKS[task_id] = {
                'status': 'starting',
                'progress': 0,
                'filename': '',
                'error': None,
                'start_time': datetime.now().isoformat(),
                'post_processing': post_process is not None
            }
        
        def progress_hook(d):
            if task_id and task_id in DOWNLOAD_TASKS:
                if d['status'] == 'downloading':
                    try:
                        percent = d.get('_percent_str', '0%').replace('%', '')
                        DOWNLOAD_TASKS[task_id]['progress'] = float(percent) * 0.7  # Reserve 30% for post-processing
                        DOWNLOAD_TASKS[task_id]['status'] = 'downloading'
                        DOWNLOAD_TASKS[task_id]['filename'] = d.get('filename', '')
                    except (ValueError, TypeError):
                        pass
                elif d['status'] == 'finished':
                    if post_process:
                        DOWNLOAD_TASKS[task_id]['status'] = 'post_processing'
                        DOWNLOAD_TASKS[task_id]['progress'] = 70
                    else:
                        DOWNLOAD_TASKS[task_id]['status'] = 'finished'
                        DOWNLOAD_TASKS[task_id]['progress'] = 100
                    DOWNLOAD_TASKS[task_id]['filename'] = d.get('filename', '')
        
        output_path = os.path.join(TEMP_DIR, '%(title)s.%(ext)s')
        
        # Enhanced yt-dlp options with FFmpeg integration
        ydl_opts = {
            'format': format_selector,
            'outtmpl': output_path,
            'quiet': True,
            'progress_hooks': [progress_hook] if task_id else [],
            'writesubtitles': download_subtitles,
            'writeautomaticsub': download_subtitles,
            'subtitleslangs': ['en', 'en-US', 'en-GB'] if download_subtitles else []
        }
        
        # Add FFmpeg post-processing if available
        if self.ffmpeg_processor.ffmpeg_available and not post_process:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4'
            }]
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                title = info.get('title', 'download')
                
                # Apply custom post-processing if specified
                if post_process and self.ffmpeg_processor.ffmpeg_available:
                    if task_id:
                        DOWNLOAD_TASKS[task_id]['status'] = 'post_processing'
                        DOWNLOAD_TASKS[task_id]['progress'] = 75
                    
                    processed_filename = self._apply_post_processing(filename, post_process)
                    
                    if task_id:
                        DOWNLOAD_TASKS[task_id]['progress'] = 100
                        DOWNLOAD_TASKS[task_id]['status'] = 'completed'
                        DOWNLOAD_TASKS[task_id]['filename'] = processed_filename
                    
                    return processed_filename, title
                
                if task_id:
                    DOWNLOAD_TASKS[task_id]['status'] = 'completed'
                    DOWNLOAD_TASKS[task_id]['filename'] = filename
                    DOWNLOAD_TASKS[task_id]['progress'] = 100
                
                return filename, title
        except Exception as e:
            if task_id:
                DOWNLOAD_TASKS[task_id]['status'] = 'error'
                DOWNLOAD_TASKS[task_id]['error'] = str(e)
            raise Exception(f"Error downloading video: {str(e)}")
    
    def _apply_post_processing(self, filename, post_process_config):
        """Apply FFmpeg post-processing based on configuration"""
        try:
            action = post_process_config.get('action')
            
            if action == 'compress':
                level = post_process_config.get('level', 'medium')
                return self.ffmpeg_processor.compress_video(filename, level)
            
            elif action == 'extract_audio':
                format_type = post_process_config.get('format', 'mp3')
                quality = post_process_config.get('quality', '192k')
                return self.ffmpeg_processor.extract_audio(filename, format_type, quality)
            
            elif action == 'convert':
                format_type = post_process_config.get('format', 'mp4')
                quality = post_process_config.get('quality', 'medium')
                resolution = post_process_config.get('resolution')
                return self.ffmpeg_processor.convert_video(filename, format_type, quality, resolution)
            
            elif action == 'trim':
                start_time = post_process_config.get('start_time', '00:00:00')
                duration = post_process_config.get('duration', '00:01:00')
                return self.ffmpeg_processor.trim_video(filename, start_time, duration)
            
            elif action == 'watermark':
                text = post_process_config.get('text', 'Downloaded with Advanced Downloader')
                position = post_process_config.get('position', 'bottom-right')
                return self.ffmpeg_processor.add_watermark(filename, text, position)
            
            else:
                return filename
                
        except Exception as e:
            print(f"Post-processing error: {e}")
            return filename  # Return original file if processing fails
    
    def batch_download(self, urls, format_selector='best', task_id=None, post_process=None):
        """Download multiple URLs as a batch with optional post-processing"""
        if task_id:
            DOWNLOAD_TASKS[task_id] = {
                'status': 'starting',
                'progress': 0,
                'total_files': len(urls),
                'completed_files': 0,
                'files': [],
                'errors': [],
                'start_time': datetime.now().isoformat(),
                'post_processing': post_process is not None
            }
        
        downloaded_files = []
        errors = []
        
        for i, url in enumerate(urls):
            try:
                if task_id:
                    DOWNLOAD_TASKS[task_id]['status'] = f'downloading {i+1}/{len(urls)}'
                
                filename, title = self.download_video(url, format_selector, post_process=post_process)
                downloaded_files.append({'filename': filename, 'title': title, 'url': url})
                
                if task_id:
                    DOWNLOAD_TASKS[task_id]['completed_files'] = i + 1
                    DOWNLOAD_TASKS[task_id]['progress'] = ((i + 1) / len(urls)) * 100
                    DOWNLOAD_TASKS[task_id]['files'].append({'title': title, 'status': 'completed'})
                
            except Exception as e:
                error_info = {'url': url, 'error': str(e)}
                errors.append(error_info)
                
                if task_id:
                    DOWNLOAD_TASKS[task_id]['errors'].append(error_info)
                    DOWNLOAD_TASKS[task_id]['files'].append({'url': url, 'status': 'error', 'error': str(e)})
        
        if task_id:
            DOWNLOAD_TASKS[task_id]['status'] = 'completed'
            DOWNLOAD_TASKS[task_id]['progress'] = 100
        
        return downloaded_files, errors
    
    def create_zip_archive(self, files):
        """Create a ZIP archive of downloaded files"""
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for file_info in files:
                if os.path.exists(file_info['filename']):
                    zip_file.write(file_info['filename'], 
                                 os.path.basename(file_info['filename']))
        
        zip_buffer.seek(0)
        return zip_buffer

downloader = AdvancedSocialMediaDownloader()

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'message': 'Advanced Social Media Downloader API with FFmpeg',
        'version': '2.1.0',
        'supported_platforms': list(downloader.supported_platforms.values()),
        'ffmpeg_available': downloader.ffmpeg_processor.ffmpeg_available,
        'features': [
            'Multi-format downloads',
            'Batch processing',
            'Progress tracking',
            'Subtitle downloads',
            'Advanced format selection',
            'ZIP archive creation',
            'Video compression',
            'Audio extraction',
            'Format conversion',
            'Resolution scaling',
            'Video trimming',
            'Watermarking'
        ]
    })

@app.route('/api/validate', methods=['POST'])
def validate_url():
    """Validate URL endpoint"""
    try:
        data = request.get_json()
        url = data.get('url')
        
        is_valid, message = downloader.validate_url(url)
        
        return jsonify({
            'valid': is_valid,
            'message': message,
            'platform': downloader.get_platform(url) if is_valid else None
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/info', methods=['POST'])
def get_video_info():
    """Enhanced video information endpoint"""
    try:
        data = request.get_json()
        url = data.get('url')
        include_formats = data.get('include_formats', True)
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        is_valid, message = downloader.validate_url(url)
        if not is_valid:
            return jsonify({'error': message}), 400
        
        info = downloader.get_video_info(url, include_formats)
        return jsonify({
            'success': True,
            'data': info
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    """Enhanced download endpoint with FFmpeg processing options"""
    try:
        data = request.get_json()
        url = data.get('url')
        format_selector = data.get('format', 'best')
        download_subtitles = data.get('subtitles', False)
        post_process = data.get('post_process')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Use preset if provided
        if format_selector in downloader.format_presets:
            format_selector = downloader.format_presets[format_selector]
        
        # Use processing preset if provided
        if post_process and isinstance(post_process, str) and post_process in downloader.processing_presets:
            post_process = downloader.processing_presets[post_process]
        
        filepath, title = downloader.download_video(
            url, format_selector, 
            download_subtitles=download_subtitles, 
            post_process=post_process
        )
        
        if os.path.exists(filepath):
            return send_file(
                filepath,
                as_attachment=True,
                download_name=f"{title}.{filepath.split('.')[-1]}"
            )
        else:
            return jsonify({'error': 'Download failed'}), 500
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/download/async', methods=['POST'])
def async_download():
    """Start asynchronous download with progress tracking and FFmpeg processing"""
    try:
        data = request.get_json()
        url = data.get('url')
        format_selector = data.get('format', 'best')
        download_subtitles = data.get('subtitles', False)
        post_process = data.get('post_process')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        task_id = str(uuid.uuid4())
        
        # Use preset if provided
        if format_selector in downloader.format_presets:
            format_selector = downloader.format_presets[format_selector]
        
        # Use processing preset if provided
        if post_process and isinstance(post_process, str) and post_process in downloader.processing_presets:
            post_process = downloader.processing_presets[post_process]
        
        # Start download in background thread
        thread = threading.Thread(
            target=downloader.download_video,
            args=(url, format_selector, task_id, download_subtitles, post_process)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': 'Download started',
            'ffmpeg_processing': post_process is not None
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/batch-download', methods=['POST'])
def batch_download():
    """Batch download multiple URLs with FFmpeg processing"""
    try:
        data = request.get_json()
        urls = data.get('urls', [])
        format_selector = data.get('format', 'best')
        post_process = data.get('post_process')
        
        if not urls or not isinstance(urls, list):
            return jsonify({'error': 'URLs array is required'}), 400
        
        if len(urls) > 50:  # Limit batch size
            return jsonify({'error': 'Maximum 50 URLs per batch'}), 400
        
        task_id = str(uuid.uuid4())
        
        # Use preset if provided
        if format_selector in downloader.format_presets:
            format_selector = downloader.format_presets[format_selector]
        
        # Use processing preset if provided
        if post_process and isinstance(post_process, str) and post_process in downloader.processing_presets:
            post_process = downloader.processing_presets[post_process]
        
        # Start batch download in background
        thread = threading.Thread(
            target=downloader.batch_download,
            args=(urls, format_selector, task_id, post_process)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f'Batch download started for {len(urls)} URLs',
            'ffmpeg_processing': post_process is not None
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/process-video', methods=['POST'])
def process_video():
    """Process uploaded video with FFmpeg"""
    try:
        if not downloader.ffmpeg_processor.ffmpeg_available:
            return jsonify({'error': 'FFmpeg is not available'}), 400
        
        data = request.get_json()
        file_path = data.get('file_path')
        processing_type = data.get('type')
        options = data.get('options', {})
        
        if not file_path or not os.path.exists(file_path):
            return jsonify({'error': 'Valid file path required'}), 400
        
        result_path = None
        
        if processing_type == 'compress':
            level = options.get('level', 'medium')
            result_path = downloader.ffmpeg_processor.compress_video(file_path, level)
        
        elif processing_type == 'extract_audio':
            format_type = options.get('format', 'mp3')
            quality = options.get('quality', '192k')
            result_path = downloader.ffmpeg_processor.extract_audio(file_path, format_type, quality)
        
        elif processing_type == 'convert':
            format_type = options.get('format', 'mp4')
            quality = options.get('quality', 'medium')
            resolution = options.get('resolution')
            result_path = downloader.ffmpeg_processor.convert_video(file_path, format_type, quality, resolution)
        
        elif processing_type == 'trim':
            start_time = options.get('start_time', '00:00:00')
            duration = options.get('duration', '00:01:00')
            result_path = downloader.ffmpeg_processor.trim_video(file_path, start_time, duration)
        
        elif processing_type == 'watermark':
            text = options.get('text', 'Processed Video')
            position = options.get('position', 'bottom-right')
            result_path = downloader.ffmpeg_processor.add_watermark(file_path, text, position)
        
        elif processing_type == 'info':
            video_info = downloader.ffmpeg_processor.get_video_info(file_path)
            return jsonify({
                'success': True,
                'info': video_info
            })
        
        else:
            return jsonify({'error': 'Invalid processing type'}), 400
        
        if result_path and os.path.exists(result_path):
            return send_file(
                result_path,
                as_attachment=True,
                download_name=os.path.basename(result_path)
            )
        else:
            return jsonify({'error': 'Processing failed'}), 500
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/merge-videos', methods=['POST'])
def merge_videos():
    """Merge multiple videos into one"""
    try:
        if not downloader.ffmpeg_processor.ffmpeg_available:
            return jsonify({'error': 'FFmpeg is not available'}), 400
        
        data = request.get_json()
        file_paths = data.get('file_paths', [])
        output_format = data.get('format', 'mp4')
        
        if len(file_paths) < 2:
            return jsonify({'error': 'At least 2 video files required'}), 400
        
        # Verify all files exist
        for path in file_paths:
            if not os.path.exists(path):
                return jsonify({'error': f'File not found: {path}'}), 400
        
        result_path = downloader.ffmpeg_processor.merge_videos(file_paths, output_format)
        
        if result_path and os.path.exists(result_path):
            return send_file(
                result_path,
                as_attachment=True,
                download_name=f'merged_video.{output_format}'
            )
        else:
            return jsonify({'error': 'Merge failed'}), 500
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/progress/<task_id>', methods=['GET'])
def get_download_progress(task_id):
    """Get download progress for a task"""
    if task_id not in DOWNLOAD_TASKS:
        return jsonify({'error': 'Task not found'}), 404
    
    task = DOWNLOAD_TASKS[task_id]
    
    # Clean up completed tasks older than 1 hour
    if task['status'] in ['completed', 'error']:
        try:
            start_time = datetime.fromisoformat(task['start_time'])
            if (datetime.now() - start_time).total_seconds() > 3600:
                del DOWNLOAD_TASKS[task_id]
                return jsonify({'error': 'Task expired'}), 404
        except:
            pass
    
    return jsonify(task)

@app.route('/api/download/file/<task_id>', methods=['GET'])
def download_completed_file(task_id):
    """Download completed file by task ID"""
    if task_id not in DOWNLOAD_TASKS:
        return jsonify({'error': 'Task not found'}), 404
    
    task = DOWNLOAD_TASKS[task_id]
    
    if task['status'] != 'completed':
        return jsonify({'error': 'Download not completed'}), 400
    
    filename = task.get('filename')
    if not filename or not os.path.exists(filename):
        return jsonify({'error': 'File not found'}), 404
    
    return send_file(
        filename,
        as_attachment=True,
        download_name=os.path.basename(filename)
    )

@app.route('/api/formats', methods=['GET'])
def get_format_presets():
    """Get available format presets including FFmpeg processing options"""
    return jsonify({
        'download_presets': downloader.format_presets,
        'processing_presets': downloader.processing_presets,
        'descriptions': {
            'best_video': 'Best quality video (MP4)',
            'best_audio': 'Best quality audio only',
            'worst_video': 'Smallest file size video',
            'hd_720p': '720p HD video',
            'hd_1080p': '1080p Full HD video',
            '4k': '4K Ultra HD video (if available)',
            'audio_only': 'Audio only (various formats)',
            'video_only': 'Video only (no audio)',
            'compress_high': 'High quality compression (smaller file)',
            'compress_medium': 'Medium quality compression',
            'compress_low': 'Low quality compression (smallest file)',
            'extract_audio_mp3': 'Extract audio as MP3',
            'extract_audio_aac': 'Extract audio as AAC',
            'convert_to_mp4': 'Convert to MP4 format',
            'convert_to_webm': 'Convert to WebM format',
            'scale_720p': 'Scale video to 720p resolution',
            'scale_1080p': 'Scale video to 1080p resolution'
        },
        'ffmpeg_available': downloader.ffmpeg_processor.ffmpeg_available
    })

@app.route('/api/ffmpeg/status', methods=['GET'])
def ffmpeg_status():
    """Check FFmpeg availability and capabilities"""
    processor = downloader.ffmpeg_processor
    return jsonify({
        'available': processor.ffmpeg_available,
        'capabilities': [
            'Video compression',
            'Audio extraction',
            'Format conversion',
            'Resolution scaling',
            'Video trimming',
            'Video merging',
            'Watermarking',
            'Video analysis'
        ] if processor.ffmpeg_available else [],
        'supported_formats': {
            'input': ['mp4', 'avi', 'mov', 'mkv', 'webm', 'flv', 'm4v'],
            'output': ['mp4', 'avi', 'mov', 'mkv', 'webm'],
            'audio': ['mp3', 'aac', 'wav', 'ogg', 'flac']
        } if processor.ffmpeg_available else {}
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Enhanced health check with FFmpeg status"""
    return jsonify({
        'status': 'healthy',
        'version': '2.1.0',
        'temp_dir': TEMP_DIR,
        'supported_platforms': len(downloader.supported_platforms),
        'active_tasks': len(DOWNLOAD_TASKS),
        'ffmpeg_available': downloader.ffmpeg_processor.ffmpeg_available,
        'features': [
            'multi-format', 'batch-download', 'progress-tracking', 
            'subtitles', 'ffmpeg-processing', 'video-compression',
            'audio-extraction', 'format-conversion', 'video-merging'
        ]
    })

@app.route('/api/cleanup', methods=['POST'])
def cleanup_files():
    """Clean up temporary files"""
    try:
        cleaned = 0
        for file in os.listdir(TEMP_DIR):
            file_path = os.path.join(TEMP_DIR, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
                cleaned += 1
        
        # Clean up expired tasks
        current_time = datetime.now()
        expired_tasks = []
        for task_id, task in DOWNLOAD_TASKS.items():
            try:
                start_time = datetime.fromisoformat(task['start_time'])
                if (current_time - start_time).total_seconds() > 3600:
                    expired_tasks.append(task_id)
            except:
                expired_tasks.append(task_id)
        
        for task_id in expired_tasks:
            del DOWNLOAD_TASKS[task_id]
        
        return jsonify({
            'success': True,
            'files_cleaned': cleaned,
            'tasks_cleaned': len(expired_tasks)
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Error handlers
@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({'error': 'File too large'}), 413

@app.errorhandler(500)
def internal_server_error(error):
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    # Check FFmpeg availability on startup
    print("=== Advanced Social Media Downloader with FFmpeg ===")
    print(f"FFmpeg Available: {downloader.ffmpeg_processor.ffmpeg_available}")
    print(f"Temp Directory: {TEMP_DIR}")
    print(f"Supported Platforms: {len(downloader.supported_platforms)}")
    print("=== Starting Server ===")
    
    app.run(host='0.0.0.0', port=port, debug=True)
