# Social Media Downloader Backend

A Flask-based backend API for downloading videos from various social media platforms using yt-dlp.

## Features

- Support for multiple platforms: YouTube, Twitter/X, Instagram, TikTok, Facebook, Vimeo
- Video information extraction (title, duration, uploader, etc.)
- Multiple quality options
- CORS enabled for frontend integration
- Health check endpoint
- Error handling and validation

## API Endpoints

### GET /
Home endpoint with API information

### POST /api/info
Get video information without downloading
```json
{
  "url": "https://www.youtube.com/watch?v=example"
}
```

### POST /api/download
Download video with specified quality
```json
{
  "url": "https://www.youtube.com/watch?v=example",
  "quality": "best"
}
```

### GET /api/health
Health check endpoint

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python main.py
```

## Deployment

This backend is configured for Render deployment using the `render.yaml` file.

1. Connect your repository to Render
2. The service will automatically deploy using the configuration in `render.yaml`

## Environment Variables

- `PORT`: Server port (default: 5000)
- `FLASK_ENV`: Flask environment (development/production)

## Dependencies

- Flask: Web framework
- Flask-CORS: Cross-origin resource sharing
- yt-dlp: Video download library
- requests: HTTP library
- gunicorn: WSGI server for production
