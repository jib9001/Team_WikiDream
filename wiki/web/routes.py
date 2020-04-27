"""
    Routes
    ~~~~~~
"""
from flask import Blueprint
from flask import flash
from flask import redirect
from flask import render_template
from flask import request
from flask import session
from flask import url_for
from flask import Markup
from flask_login import current_user
from flask_login import login_required
from flask_login import login_user
from flask_login import logout_user

from wiki.core import Processor
from wiki.web import current_users
from wiki.web import current_wiki
from wiki.web.forms import EditorForm
from wiki.web.forms import RatingForm
from wiki.web.forms import LoginForm
from wiki.web.forms import SearchForm
from wiki.web.forms import URLForm
from wiki.web.user import protect

from difflib import ndiff

bp = Blueprint('wiki', __name__)
user = ''


@bp.route('/')
@protect
def home():
    page = current_wiki.get('home')
    if page:
        return display('home')
    return render_template('home.html')


@bp.route('/index/')
@protect
def index():
    pages = current_wiki.index()
    return render_template('index.html', pages=pages)


@bp.route('/<path:url>/')
@protect
def display(url):
    page = current_wiki.get_or_404(url)
    return render_template('page.html', page=page)


@bp.route('/create/', methods=['GET', 'POST'])
@protect
def create():
    form = URLForm()
    if form.validate_on_submit():
        return redirect(url_for(
            'wiki.edit', url=form.clean_url(form.url.data)))
    return render_template('create.html', form=form)


@bp.route('/edit/<path:url>/', methods=['GET', 'POST'])
@protect
def edit(url):
    page = current_wiki.get(url)
    form = EditorForm(obj=page)
    if form.validate_on_submit():
        if not page:
            page = current_wiki.get_bare(url)
        form.populate_obj(page)
        page.save(session["user_id"])
        flash('"%s" was saved.' % page.title, 'success')
        return redirect(url_for('wiki.display', url=url))
    return render_template('editor.html', form=form, page=page)


@bp.route('/rating/<path:url>/', methods=['GET', 'POST'])
def rating(url):
    page = current_wiki.get(url)
    form = RatingForm()
    if form.validate_on_submit():
        if not page:
            page = current_wiki.get_bare(url)
        form.populate_obj(page)
        page.save()
        flash('"%s" was saved.' % page.title, 'success')
        return redirect(url_for('wiki.display', url=url))
    return render_template('page.html', form=form, page=page)


@bp.route('/preview/', methods=['POST'])
@protect
def preview():
    data = {}
    processor = Processor(request.form['body'])
    data['html'], data['body'], data['meta'] = processor.process()
    return data['html']


@bp.route('/move/<path:url>/', methods=['GET', 'POST'])
@protect
def move(url):
    page = current_wiki.get_or_404(url)
    form = URLForm(obj=page)
    if form.validate_on_submit():
        newurl = form.url.data
        current_wiki.move(url, newurl)
        return redirect(url_for('wiki.display', url=newurl))
    return render_template('move.html', form=form, page=page)


@bp.route('/delete/<path:url>/')
@protect
def delete(url):
    page = current_wiki.get_or_404(url)
    current_wiki.delete(url)
    flash('Page "%s" was deleted.' % page.title, 'success')
    return redirect(url_for('wiki.home'))


@bp.route('/tags/')
@protect
def tags():
    tags = current_wiki.get_tags()
    return render_template('tags.html', tags=tags)


@bp.route('/tag/<string:name>/')
@protect
def tag(name):
    tagged = current_wiki.index_by_tag(name)
    return render_template('tag.html', pages=tagged, tag=name)


@bp.route('/search/', methods=['GET', 'POST'])
@protect
def search():
    form = SearchForm()
    if form.validate_on_submit():
        results = current_wiki.search(form.term.data, form.ignore_case.data)
        return render_template('search.html', form=form,
                               results=results, search=form.term.data)
    return render_template('search.html', form=form, search=None)


@bp.route('/history/<path:url>/')
@protect
def history(url):
    """
    This route handles showing the pages history.
    :param url: The url of the page for which you want the history of
    :return: Show the history of the page
    """
    page = current_wiki.get_or_404(url)
    return render_template('history.html', history=page.history, page=page)


@bp.route('/history/<path:url>/<string:name>')
@protect
def history_user(url, name):
    """
    This route handles displaying the additions and subtractions to the page that a user made.
    :param url: The url of the page that was edited
    :param name: The name of the user who edited the page
    :return: Show a page the highlights the differences between the current content and the previous content
    """
    # get the page passed
    page = current_wiki.get_or_404(url)

    # The timestamp of the edit is passed as a query param
    # Use it to get the edit we're interested in
    current_entry = page.history.entries[request.args.get("time")]
    previous_entry = current_entry
    current_entry_idx = page.history.entryKeys.index(request.args.get("time"))

    # Get the most recent edit made before the current one
    if current_entry_idx + 1 < len(page.history.entryKeys):
        previous_entry_idx = current_entry_idx + 1
        previous_entry_key = page.history.entryKeys[previous_entry_idx]
        previous_entry = page.history.entries[previous_entry_key]

    # Generate a difference highlighting the additions and subtractions from the content
    diff = ndiff(previous_entry["version"], current_entry["version"])
    adding = False
    first_add = True
    subtracting = False
    first_subtract = True
    diff_length = len(list(diff))
    edits = ""
    for i, s in enumerate(ndiff(previous_entry["version"], current_entry["version"])):

        if (s[0] != '+' or i + 1 == diff_length) and adding is True:
            adding = False
            first_add = True
            edits += "</span>"

        if (s[0] != '-' or i + 1 == diff_length) and subtracting is True:
            subtracting = False
            first_subtract = True
            edits += "</span>"

        if s[0] == '+':
            if first_add is True:
                edits += "<span class=addition>"
                first_add = False
            adding = True
            edits += s[2]

        if s[0] == '-':
            if first_subtract is True:
                edits += "<span class=subtraction>"
                first_subtract = False
            subtracting = True
            edits += s[2]

        if s[0] == ' ':
            edits += s[2]

    safe_edits = Markup(edits)
    return render_template('user_based_history.html', edits=safe_edits, page=page, user=name, time=request.args.get("time"))


@bp.route('/user/login/', methods=['GET', 'POST'])
def user_login():
    form = LoginForm()
    if form.validate_on_submit():
        user = current_users.get_user(form.name.data)
        login_user(user)
        user.set('authenticated', True)
        flash('Login successful.', 'success')
        return redirect(request.args.get("next") or url_for('wiki.index'))
    return render_template('login.html', form=form)


@bp.route('/user/logout/')
@login_required
def user_logout():
    current_user.set('authenticated', False)
    logout_user()
    flash('Logout successful.', 'success')
    return redirect(url_for('wiki.index'))


@bp.route('/user/')
def user_index():
    pass


@bp.route('/user/create/')
def user_create():
    pass


@bp.route('/user/<int:user_id>/')
def user_admin(user_id):
    pass


@bp.route('/user/delete/<int:user_id>/')
def user_delete(user_id):
    pass


"""
    Error Handlers
    ~~~~~~~~~~~~~~
"""


@bp.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404
