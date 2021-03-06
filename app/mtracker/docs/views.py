import os
from docutils import core

from django.views.decorators.cache import cache_page
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.conf import settings


def doc_parts(input_string):
    parts = core.publish_parts(source=input_string, writer_name='html')
    return parts


@cache_page(10 * 60)
def docs_readme(request):
    """Reads README.rst from repository root, converts it using docutils and
    renders it into a template.

    TODO: generate sphinxdoc/readme.thml file on deployment instead in this view
    """
    file_path = os.path.join(settings.ROOT_PATH, 'README.rst')
    file = open(file_path, 'r')
    parts = doc_parts(file.read())
    context = {'content': parts['html_body']}
    return render_to_response(
        'sphinxdoc/readme.html', RequestContext(request, context))
