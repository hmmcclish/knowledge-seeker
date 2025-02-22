import flask
import io
import textwrap as tw
from base64 import b64decode
from datetime import timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

import knowledgeseeker.ffmpeg as ff
from knowledgeseeker.database import get_db, match_episode
from knowledgeseeker.utils import set_expires


bp = flask.Blueprint('clips', __name__)

TEXT_VMARGIN = 0.1
TEXT_SPACING = 4
JPEG_QUALITY = 85


@bp.route('/<season>/<episode>/<int:ms>/pic')
@set_expires
@match_episode
def snapshot(season_id, episode_id, ms):
    # Load PNG from database.
    cur = get_db().cursor()
    cur.execute(
        'SELECT png FROM snapshot'
        ' WHERE episode_id=:episode_id AND ms=:ms',
        { 'episode_id': episode_id, 'ms': ms })
    res = cur.fetchone()
    if res is None:
        flask.abort(404, 'time not found')
    image = Image.open(io.BytesIO(res['png']))

    # Draw text if requested.
    top_text = (b64decode(flask.request.args.get('topb64', ''))
        .decode('ascii', 'ignore'))
    bottom_text = (b64decode(flask.request.args.get('btmb64', ''))
        .decode('ascii', 'ignore'))
    if top_text != '' or bottom_text != '':
        drawtext(image, top_text, bottom_text)

    # Return as compressed JPEG.
    res = io.BytesIO()
    image.save(res, 'jpeg', quality=JPEG_QUALITY)
    return flask.Response(res.getvalue(), mimetype='image/jpeg')


@bp.route('/<season>/<episode>/<int:ms>/pic/tiny')
@set_expires
@match_episode
def snapshot_tiny(season_id, episode_id, ms):
    cur = get_db().cursor()
    cur.execute(
        'SELECT jpeg FROM snapshot_tiny '
        ' WHERE episode_id=:episode_id AND ms=:ms',
        { 'episode_id': episode_id, 'ms': ms })
    res = cur.fetchone()
    if res is None:
        flask.abort(404, 'time not found')
    return flask.Response(res['jpeg'], mimetype='image/jpeg')


def drawtext(image, top_text, bottom_text):
    MAX_WIDTH = flask.current_app.config.get('PIL_MAXWIDTH')
    MAX_LENGTH = MAX_WIDTH*2

    font_path = flask.current_app.config.get('PIL_FONT', None)
    font = (ImageFont.truetype(
            font=str(font_path),
            size=flask.current_app.config.get('PIL_FONT_SIZE'))
        if font_path is not None else None)
    draw = ImageDraw.Draw(image)
    def wrap(t):
        return '\n'.join(tw.wrap(t, width=MAX_WIDTH))

    if top_text != '':
        text = wrap(top_text[:MAX_LENGTH])
        size = draw.multiline_textsize(text, font=font, spacing=TEXT_SPACING)
        pos = (round(image.width/2 - size[0]/2), round(TEXT_VMARGIN*image.height))

        blurred = Image.new('RGBA', image.size)
        blurredDraw = ImageDraw.Draw(blurred)
        blurredDraw.multiline_text(pos, text, fill='black', font=font,
                                   spacing=TEXT_SPACING, align='center')
        blurred = blurred.filter(ImageFilter.BoxBlur(7))

        # Paste soft text onto background
        image.paste(blurred,blurred)

        draw.multiline_text(pos, text, font=font,
                            spacing=TEXT_SPACING, align='center')

    if bottom_text != '':
        text = wrap(bottom_text[:MAX_LENGTH])
        size = draw.multiline_textsize(text, font=font, spacing=TEXT_SPACING)
        pos = (round(image.width/2 - size[0]/2),
               image.height - round(TEXT_VMARGIN*image.height) - size[1])

        blurred = Image.new('RGBA', image.size)
        blurredDraw = ImageDraw.Draw(blurred)
        blurredDraw.multiline_text(pos, text, fill='black', font=font,
                                   spacing=TEXT_SPACING, align='center')
        blurred = blurred.filter(ImageFilter.BoxBlur(7))

        # Paste soft text onto background
        image.paste(blurred,blurred)

        draw.multiline_text(pos, text, font=font,
                            spacing=TEXT_SPACING, align='center')


@bp.route('/<season>/<episode>/<int:ms1>/<int:ms2>/gif')
@set_expires
@match_episode
def gif(season_id, episode_id, ms1, ms2):
    if not check_range(episode_id, ms1, ms2,
                       flask.current_app.config.get('MAX_GIF_LENGTH')):
        flask.abort(400, 'bad time range')

    cur = get_db().cursor()
    cur.execute('SELECT video_path FROM episode WHERE id=:episode_id',
                { 'episode_id': episode_id })
    res = cur.fetchone()
    video_path = res['video_path']

    return flask.Response(ff.make_gif(video_path, ms1, ms2), mimetype='image/gif')


@bp.route('/<season>/<episode>/<int:ms1>/<int:ms2>/gif/sub')
@set_expires
@match_episode
def gif_with_subtitles(season_id, episode_id, ms1, ms2):
    if not check_range(episode_id, ms1, ms2,
                       flask.current_app.config.get('MAX_GIF_LENGTH')):
        flask.abort(400, 'bad time range')

    cur = get_db().cursor()
    cur.execute(
        'SELECT video_path, subtitles_path FROM episode WHERE id=:episode_id',
        { 'episode_id': episode_id })
    res = cur.fetchone()
    video_path = res['video_path']
    subtitles_path = res['subtitles_path']

    return flask.Response(
        ff.make_gif_with_subtitles(video_path, subtitles_path, ms1, ms2),
        mimetype='image/gif')


@bp.route('/<season>/<episode>/<int:ms1>/<int:ms2>/webm')
@set_expires
@match_episode
def webm(season_id, episode_id, ms1, ms2):
    if not check_range(episode_id, ms1, ms2,
                       flask.current_app.config.get('MAX_WEBM_LENGTH')):
        flask.abort(400, 'bad time range')

    cur = get_db().cursor()
    cur.execute('SELECT video_path FROM episode WHERE id=:episode_id',
                { 'episode_id': episode_id })
    res = cur.fetchone()
    video_path = res['video_path']

    return flask.Response(ff.make_webm(video_path, ms1, ms2), mimetype='video/webm')


@bp.route('/<season>/<episode>/<int:ms1>/<int:ms2>/webm/sub')
@set_expires
@match_episode
def webm_with_subtitles(season_id, episode_id, ms1, ms2):
    if not check_range(episode_id, ms1, ms2,
                       flask.current_app.config.get('MAX_WEBM_LENGTH')):
        flask.abort(400, 'bad time range')

    cur = get_db().cursor()
    cur.execute(
        'SELECT video_path, subtitles_path FROM episode WHERE id=:episode_id',
        { 'episode_id': episode_id })
    res = cur.fetchone()
    video_path = res['video_path']
    subtitles_path = res['subtitles_path']

    return flask.Response(
        ff.make_webm_with_subtitles(video_path, subtitles_path, ms1, ms2),
        mimetype='video/webm')


def check_range(episode_id, ms1, ms2, max_length):
    if ms1 >= ms2 or ms1 < 0 or ms2 - ms1 > max_length.total_seconds()*1000:
        return False
    else:
        cur = get_db().cursor()
        cur.execute('SELECT duration FROM episode WHERE id=:episode_id',
                    { 'episode_id': episode_id })
        res = cur.fetchone()
        return (ms2 <= res['duration']
                and check_time(episode_id, ms1) and check_time(episode_id, ms2))


def check_time(episode_id, ms):
    cur = get_db().cursor()
    cur.execute('SELECT ms FROM snapshot WHERE episode_id=:episode_id AND ms=:ms',
                { 'episode_id': episode_id, 'ms': ms })
    return cur.fetchone() is not None

