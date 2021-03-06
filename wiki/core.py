"""
    Wiki core
    ~~~~~~~~~
"""
from collections import OrderedDict
from io import open
import os
import re

from flask import abort
from flask import url_for

import markdown
import json
import datetime


def clean_url(url):
    """
        Cleans the url and corrects various errors. Removes multiple
        spaces and all leading and trailing spaces. Changes spaces
        to underscores and makes all characters lowercase. Also
        takes care of Windows style folders use.

        :param str url: the url to clean


        :returns: the cleaned url
        :rtype: str
    """
    url = re.sub('[ ]{2,}', ' ', url).strip()
    url = url.lower().replace(' ', '_')
    url = url.replace('\\\\', '/').replace('\\', '/')
    return url


def wikilink(text, url_formatter=None):
    """
        Processes Wikilink syntax "[[Link]]" within the html body.
        This is intended to be run after content has been processed
        by markdown and is already HTML.

        :param str text: the html to highlight wiki links in.
        :param function url_formatter: which URL formatter to use,
            will by default use the flask url formatter

        Syntax:
            This accepts Wikilink syntax in the form of [[WikiLink]] or
            [[url/location|LinkName]]. Everything is referenced from the
            base location "/", therefore sub-pages need to use the
            [[page/subpage|Subpage]].

        :returns: the processed html
        :rtype: str
    """
    if url_formatter is None:
        url_formatter = url_for
    link_regex = re.compile(
        r"((?<!\<code\>)\[\[([^<].+?) \s*([|] \s* (.+?) \s*)?]])",
        re.X | re.U
    )
    for i in link_regex.findall(text):
        title = [i[-1] if i[-1] else i[1]][0]
        url = clean_url(i[1])
        html_url = "<a href='{0}'>{1}</a>".format(
            url_formatter('wiki.display', url=url),
            title
        )
        text = re.sub(link_regex, html_url, text, count=1)
    return text


class Processor(object):
    """
        The processor handles the processing of file content into
        metadata and markdown and takes care of the rendering.

        It also offers some helper methods that can be used for various
        cases.
    """

    preprocessors = []
    postprocessors = [wikilink]

    def __init__(self, text):
        """
            Initialization of the processor.

            :param str text: the text to process
        """
        self.md = markdown.Markdown([
            'codehilite',
            'fenced_code',
            'meta',
            'tables'
        ])
        self.input = text
        self.markdown = None
        self.meta_raw = None

        self.pre = None
        self.html = None
        self.final = None
        self.meta = None

    def process_pre(self):
        """
            Content preprocessor.
        """
        current = self.input
        for processor in self.preprocessors:
            current = processor(current)
        self.pre = current

    def process_markdown(self):
        """
            Convert to HTML.
        """
        self.html = self.md.convert(self.pre)

    def split_raw(self):
        """
            Split text into raw meta and content.
        """
        self.meta_raw, self.markdown = self.pre.split('\n\n', 1)

    def process_meta(self):
        """
            Get metadata.

            .. warning:: Can only be called after :meth:`html` was
                called.
        """
        # the markdown meta plugin does not retain the order of the
        # entries, so we have to loop over the meta values a second
        # time to put them into a dictionary in the correct order
        self.meta = OrderedDict()
        rate_Num = 0
        times_rated = 1
        rated = 0
        metaField = self.meta_raw.split('\n')
        for line in metaField:
            key = line.split(':', 1)[0]
            rate = line.split()
            if key == 'total':
                rate_Num = int(rate[1])
            elif key == 'timesrated':
                times_rated = int(rate[1]) + 1
            elif key == 'rating':
                rated = int(rate[1])

        total = rated + rate_Num
        rated = str(total / times_rated)

        for line in metaField:
            key = line.split(':', 1)[0]
            if key == 'total':
                self.md.Meta[key.lower()] = str(total).lower()
            elif key == 'timesrated':
                self.md.Meta[key.lower()] = str(times_rated).lower()
            elif key == 'rating':
                self.md.Meta[key.lower()] = str(rated).lower()


            # markdown metadata always returns a list of lines, we will
            # reverse that here
            self.meta[key.lower()] = '\n'.join(self.md.Meta[key.lower()])

    def process_post(self):
        """
            Content postprocessor.
        """
        current = self.html
        for processor in self.postprocessors:
            current = processor(current)
        self.final = current

    def generate_contents_table(self, final):
        """
            Generates a table of contents for any page that uses level 1 headers
        """
        # Checks to see if there are any level 1 headers, after the markdown is converted
        if final.count("<h1>"):
            # Creates the necessary opening tags for our table of contents
            table_html = \
                "<div class=\"row\"><div class=\"span2\"><h3>Contents</h3><ul class='nav nav-tabs nav-stacked'>"

            # gets arrays of all indicies in the file of the opening and closing h1 tags
            header_open_loc = self.find_tags("<h1>", self.final)
            header_close_loc = self.find_tags("</h1>", self.final)

            # using the locations of the headers in the file, we can construct a table of contents
            # after grabbing the name of a header, we add it to the table of contents as a list item
            # we also add an anchor tag linked to the header further down on the page
            for i in range(len(header_open_loc)):
                header = final[header_open_loc[i] + 4:header_close_loc[i]]
                header_f = header.lower()
                header_f = header.replace(" ", "_")
                header_f = "#" + header_f
                table_html += "<li><a href=\"" + header_f + "\">" + header + "</a></li>"

            # This is where we generate the anchor tags for the headers to be linked to by the table of contents
            # It must be iterated backwards to not displace the html tags in reference to the indicies we already have
            for i in range(len(header_open_loc)-1,-1, -1):
                header = final[header_open_loc[i] + 4:header_close_loc[i]]
                header_f = header.lower()
                header_f = header.replace(" ", "_")
                final = final[:header_open_loc[i]] + "<a name=\"" + header_f + "\"></a>" + \
                    final[header_open_loc[i]:]

            # close all of the opening tags created at the beginning of this method
            # this completes all of the html that we need for the table of contents
            table_html += "</ul><br></div></div>"

            # add the table of contents to the final html conversion of the markdown for the page
            final = table_html + final

        return final

    def find_tags(self, substr, given_string):
        """
            Looks for all occurrences of a substring in a given string and returns a list of the beginning index
            of all occurrences
        """
        matches = re.finditer(substr, given_string)
        matches_positions = [match.start() for match in matches]

        return matches_positions

    def process(self):
        """
            Runs the full suite of processing on the given text, all
            pre and post processing, markdown rendering and meta data
            handling.
        """
        self.process_pre()
        self.process_markdown()
        self.split_raw()
        self.process_meta()
        self.process_post()

        self.final = self.generate_contents_table(self.final)

        return self.final, self.markdown, self.meta


class Page(object):
    def __init__(self, path, url, new=False):
        self.path = path
        self.url = url
        self._meta = OrderedDict()
        # Generate the path to the history file for this page and create a new history object with it
        history_path = path.replace("\\" + url + ".md", "/history/" + url + ".json")
        self.history = History(history_path, url)
        if not new:
            self.load()
            self.render()

    def __repr__(self):
        return "<Page: {}@{}>".format(self.url, self.path)

    def load(self):
        with open(self.path, 'r', encoding='utf-8') as f:
            self.content = f.read()

    def render(self):
        processor = Processor(self.content)
        self._html, self.body, self._meta = processor.process()

    def save(self, user, update=True):
        folder = os.path.dirname(self.path)
        if not os.path.exists(folder):
            os.makedirs(folder)

        with open(self.path, 'w', encoding='utf-8') as f:
            for key, value in list(self._meta.items()):
                line = '%s: %s\n' % (key, value)
                f.write(line)
            f.write('\n')
            f.write(self.body.replace('\r\n', '\n'))

        self.history.save(user, self.body.replace('\r\n', '\n'))

        if update:
            self.load()
            self.render()

    @property
    def meta(self):
        return self._meta

    def __getitem__(self, name):
        return self._meta[name]

    def __setitem__(self, name, value):
        self._meta[name] = value

    @property
    def html(self):
        return self._html

    def __html__(self):
        return self.html

    @property
    def title(self):
        try:
            return self['title']
        except KeyError:
            return self.url

    @title.setter
    def title(self, value):
        self['title'] = value

    @property
    def tags(self):
        try:
            return self['tags']
        except KeyError:
            return ""

    @tags.setter
    def tags(self, value):
        self['tags'] = value

    @property
    def rating(self):
        try:
            return self['rating']
        except KeyError:
            return 0

    @rating.setter
    def rating(self, value):
        self['rating'] = value

    @property
    def flag(self):
        try:
            return self['flag']
        except KeyError:
            return 0

    @flag.setter
    def flag(self, value):
        self['flag'] = value


class History(object):
    """
    This History object handles all aspects of a page's history
    """
    def __init__(self, path, url):
        """
        :param path: The path to the history file.
        :param url: The url of the page we want history for.
        """
        self.url = url
        self.path = path
        if not os.path.exists(self.path):
            self.create()
        with open(self.path, 'r') as hist:
            self.entries = json.load(hist)
            self.entryKeys = sorted(self.entries, reverse=True)

    def create(self):
        """
        Create the history file if it doesn't already exist.
        """
        with open(self.path, 'w', encoding='utf-8') as hist:
            init = "{}\n"
            hist.write(init)

    def save(self, user, version):
        """
        Save the new edit to the history file.
        :param user: The user who made the edit.
        :param version: The timestamp of when this edit was made, denoting a new version
        :return:
        """
        with open(self.path, 'w') as hist:
            self.entries[datetime.datetime.now().timestamp()] = {
                "user": user,
                "formatted-date": str(datetime.datetime.now().strftime('%b %d, %Y at %I:%M:%S %p')),
                "version": version
            }
            hist.seek(0)
            json.dump(self.entries, hist, indent=4)
            hist.truncate()


class Wiki(object):
    def __init__(self, root):
        self.root = root

    def path(self, url):
        return os.path.join(self.root, url + '.md')

    def exists(self, url):
        path = self.path(url)
        return os.path.exists(path)

    def get(self, url):
        path = self.path(url)
        # path = os.path.join(self.root, url + '.md')
        if self.exists(url):
            return Page(path, url)
        return None

    def get_or_404(self, url):
        page = self.get(url)
        if page:
            return page
        abort(404)

    def get_bare(self, url):
        path = self.path(url)
        if self.exists(url):
            return False
        return Page(path, url, new=True)

    def move(self, url, newurl):
        source = os.path.join(self.root, url) + '.md'
        target = os.path.join(self.root, newurl) + '.md'
        # normalize root path (just in case somebody defined it absolute,
        # having some '../' inside) to correctly compare it to the target
        root = os.path.normpath(self.root)
        # get root path longest common prefix with normalized target path
        common = os.path.commonprefix((root, os.path.normpath(target)))
        # common prefix length must be at least as root length is
        # otherwise there are probably some '..' links in target path leading
        # us outside defined root directory
        if len(common) < len(root):
            raise RuntimeError(
                'Possible write attempt outside content directory: '
                '%s' % newurl)
        # create folder if it does not exists yet
        folder = os.path.dirname(target)
        if not os.path.exists(folder):
            os.makedirs(folder)
        os.rename(source, target)

    def delete(self, url):
        path = self.path(url)
        page = self.get(url)
        if not self.exists(url):
            return False
        os.remove(page.history.path)
        os.remove(path)
        return True

    def index(self):
        """
            Builds up a list of all the available pages.

            :returns: a list of all the wiki pages
            :rtype: list
        """
        # make sure we always have the absolute path for fixing the
        # walk path
        pages = []
        root = os.path.abspath(self.root)
        for cur_dir, _, files in os.walk(root):
            # get the url of the current directory
            cur_dir_url = cur_dir[len(root) + 1:]
            for cur_file in files:
                path = os.path.join(cur_dir, cur_file)
                if cur_file.endswith('.md'):
                    url = clean_url(os.path.join(cur_dir_url, cur_file[:-3]))
                    page = Page(path, url)
                    pages.append(page)
        return sorted(pages, key=lambda x: x.title.lower())

    def index_by(self, key):
        """
            Get an index based on the given key.

            Will use the metadata value of the given key to group
            the existing pages.

            :param str key: the attribute to group the index on.

            :returns: Will return a dictionary where each entry holds
                a list of pages that share the given attribute.
            :rtype: dict
        """
        pages = {}
        for page in self.index():
            value = getattr(page, key)
            pre = pages.get(value, [])
            pages[value] = pre.append(page)
        return pages

    def get_by_title(self, title):
        pages = self.index(attr='title')
        return pages.get(title)

    def get_tags(self):
        pages = self.index()
        tags = {}
        for page in pages:
            pagetags = page.tags.split(',')
            for tag in pagetags:
                tag = tag.strip()
                if tag == '':
                    continue
                elif tags.get(tag):
                    tags[tag].append(page)
                else:
                    tags[tag] = [page]
        return tags

    def index_by_tag(self, tag):
        pages = self.index()
        tagged = []
        for page in pages:
            if tag in page.tags:
                tagged.append(page)
        return sorted(tagged, key=lambda x: x.title.lower())

    def search(self, term, ignore_case=True, attrs=['title', 'tags', 'body']):
        pages = self.index()
        regex = re.compile(term, re.IGNORECASE if ignore_case else 0)
        matched = []
        for page in pages:
            for attr in attrs:
                if regex.search(getattr(page, attr)):
                    matched.append(page)
                    break
        return matched
