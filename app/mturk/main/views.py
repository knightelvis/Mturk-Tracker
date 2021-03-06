import datetime
import json
import time

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.generic.simple import direct_to_template
from django.views.decorators.cache import cache_page, never_cache
from haystack.views import SearchView

import admin
import plot

from mturk.main.classification import NaiveBayesClassifier
from mturk.main.forms import HitGroupContentSearchForm
from mturk.main.models import HitGroupContent, HitGroupClass, RequesterProfile
from mturk.main.templatetags.graph import text_row_formater
# TODO: when refactoring toprequesters move them to mturk.toprequesters
from mturk.main.management.commands.toprequesters.reports import (
    ToprequestersReport)
from utils.sql import query_to_dicts, query_to_tuples


GENERAL_COLUMNS = (
    ('date', 'Date'),
    ('number', '#HITs'),
    ('number', 'Rewards($)'),
    ('number', '#Projects'),
    ('number', '#Spam Projects'),
)

DEFAULT_COLUMNS = (
    ('date', 'Date'),
    ('number', '#HITs'),
    ('number', 'Rewards($)'),
    ('number', '#Projects'),
)

ARRIVALS_COLUMNS = (
    ('date', 'Date'),
    ('number', '#HITs'),
    ('number', 'Rewards($)'),
)

HIT_DETAILS_COLUMNS = (
    ('date', 'Date'),
    ('number', '#HITs'),
)

ONE_DAY = 60 * 60 * 24
ONE_HOUR = 60 * 60

def data_formater(input):
    for cc in input:
        yield {
                'date': cc['start_time'],
                'row': (str(cc['hits']), str(cc['reward']),
                    str(cc['count']), str(cc['spam_projects'])),
        }

#@cache_page(ONE_HOUR)
def general(request):

    params = {
        'multichart': True,
        'columns': GENERAL_COLUMNS,
        'title': 'General Data'
    }

    if 'date_from' in request.GET:
        date_from = datetime.datetime(
                *time.strptime(request.GET['date_from'], '%m/%d/%Y')[:6])
    else:
        date_from = datetime.datetime.now() - datetime.timedelta(days=7)

    if 'date_to' in request.GET:
        date_to = datetime.datetime(
                *time.strptime(request.GET['date_to'], '%m/%d/%Y')[:6])
    else:
        date_to = datetime.datetime.now()

    params['date_from'] = date_from.strftime('%m/%d/%Y')
    params['date_to'] = date_to.strftime('%m/%d/%Y')

    data = data_formater(query_to_dicts('''
        select reward, hits, projects as "count", spam_projects, start_time
            from main_crawlagregates
            where start_time >= %s and start_time <= %s
            order by start_time asc
        ''', date_from, date_to))

    def _is_anomaly(a, others):
        mid = sum(map(lambda e: int(e['row'][0]), others)) / len(others)
        return abs(mid - int(a['row'][0])) > 7000

    def _fixer(a, others):
        val = sum(map(lambda e: int(e['row'][0]), others)) / len(others)
        a['row'] = (str(val), a['row'][1], a['row'][2], a['row'][3])
        return a

    if settings.DATASMOOTHING:
        params['data'] = plot.repair(list(data), _is_anomaly, _fixer, 2)
    else:
        params['data'] = list(data)

    return direct_to_template(request, 'main/graphs/timeline.html', params)


#@cache_page(ONE_DAY)
def arrivals(request):

    params = {
        'multichart': False,
        'columns': ARRIVALS_COLUMNS,
        'title': 'New Tasks/HITs/$$$ per day'
    }

    def arrivals_data_formater(input):
        for cc in input:
            yield {
                    'date': cc['start_time'],
                    'row': (str(cc['hits']), str(cc['reward'])),
            }

    date_from = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    date_to = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

    if request.method == 'GET' and 'date_from' in request.GET and 'date_to' in request.GET:

        date_from = datetime.datetime(*time.strptime(request.GET['date_from'], '%m/%d/%Y')[:6])
        date_to = datetime.datetime(*time.strptime(request.GET['date_to'], '%m/%d/%Y')[:6])
        params['date_from'] = request.GET['date_from']
        params['date_to'] = request.GET['date_to']

    data = arrivals_data_formater(query_to_dicts('''
        select date as "start_time", arrivals as "hits", arrivals_value as "reward"
        from main_daystats where date >= '%s' and date <= '%s'
    ''' % (date_from, date_to)))

    params['data'] = data

    return direct_to_template(request, 'main/graphs/timeline.html', params)


@cache_page(ONE_DAY)
def completed(request):

    params = {
        'columns': DEFAULT_COLUMNS,
        'title': 'Tasks/HITs/$$$ completed per day'
    }

    date_from = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    date_to = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

    if request.method == 'GET' and 'date_from' in request.GET and 'date_to' in request.GET:

        date_from = datetime.datetime(*time.strptime(request.GET['date_from'], '%m/%d/%Y')[:6])
        date_to = datetime.datetime(*time.strptime(request.GET['date_to'], '%m/%d/%Y')[:6])
        params['date_from'] = request.GET['date_from']
        params['date_to'] = request.GET['date_to']

    data = data_formater(query_to_dicts('''
        select date as "start_time", day_start_hits - day_end_hits as "hits", day_start_reward - day_end_reward as "reward", day_start_projects - day_end_projects as "count"
            from main_daystats where day_end_hits != 0 and date >= '%s' and date <= '%s'
    ''' % (date_from, date_to)))

    params['data'] = data

    return direct_to_template(request, 'main/graphs/timeline.html', params)


@never_cache
def top_requesters(request):
    if request.user.is_superuser:
        return admin.top_requesters(request)

    # TODO: link ui choice here
    data = ToprequestersReport.get_report_data(
        ToprequestersReport.AVAILABLE) or []

    def _top_requesters(request):
        def row_formatter(input):
            for cc in input:
                row = []
                row.append('<a href="%s">%s</a>' % (
                    reverse('requester_details',
                        kwargs={'requester_id': cc[0]}), cc[1]))
                row.append(('<a href="https://www.mturk.com/mturk/searchbar?'
                    'requesterId=%s" target="_mturk">%s</a> '
                    '(<a href="http://feed.crowdsauced.com/r/req/%s">RSS</a>)')
                           % (cc[0], cc[0], cc[0]))
                row.extend(cc[2:6])
                yield row

        columns = (
            ('string', 'Requester ID'),
            ('string', 'Requester'),
            ('number', '#Task'),
            ('number', '#HITs'),
            ('number', 'Rewards'),
            ('datetime', 'Last Posted On')
        )
        ctx = {
            'data': row_formatter(data),
            'columns': columns,
            'title': 'Top-1000 Recent Requesters',
        }

        return direct_to_template(request, 'main/graphs/table.html', ctx)

    return _top_requesters(request)

def requester_details(request, requester_id):
    if request.user.is_superuser:
        return admin.requester_details(request, requester_id)

    @cache_page(ONE_DAY)
    def _requester_details(request, requester_id):
        def row_formatter(input):

            for cc in input:
                row = []
                row.append('<a href="%s">%s</a>' % (reverse('hit_group_details',
                    kwargs={'hit_group_id': cc[3]}), cc[0]))
                row.extend(cc[1:3])
                yield row

        requster_name = HitGroupContent.objects.filter(
            requester_id=requester_id).values_list(
            'requester_name', flat=True).distinct()

        if requster_name:
            requster_name = requster_name[0]
        else:
            requster_name = requester_id

        date_from = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()

        data = query_to_tuples("""
    select
        title,
        p.reward,
        p.occurrence_date,
        p.group_id
    from main_hitgroupcontent p
        LEFT JOIN main_requesterprofile r ON p.requester_id = r.requester_id
    where
        p.requester_id = '%s'
        AND coalesce(r.is_public, true) = true
        and
        p.occurrence_date > TIMESTAMP '%s';
        """ % (requester_id, date_from))

        columns = [
            ('string', 'HIT Title'),
            ('number', 'Reward'),
            ('datetime', 'Posted'),
        ]
        ctx = {
            'data': text_row_formater(row_formatter(data)),
            'columns': tuple(columns),
            'title': 'Tasks posted during last 30 days by %s' % (requster_name),
            'user': request.user,
        }
        return direct_to_template(request, 'main/requester_details.html', ctx)

    return _requester_details(request, requester_id)


@never_cache
def hit_group_details(request, hit_group_id):

    try:
        hit_group = HitGroupContent.objects.get(group_id=hit_group_id)
        if RequesterProfile.objects.filter(requester_id=hit_group.requester_id,
            is_public=False):
            raise HitGroupContent.DoesNotExist()
    except HitGroupContent.DoesNotExist:
        messages.info(request, 'Hitgroup with id "{0}" was not found!'.format(
            hit_group_id))
        return redirect('haystack_search')

    try:
        hit_group_class = HitGroupClass.objects.get(group_id=hit_group_id)
    except ObjectDoesNotExist:
        # TODO classification should be done on all models.
        hit_group_class = None
        try:
            with open(settings.CLASSIFIER_PATH, "r") as file:
                classifier = NaiveBayesClassifier(probabilities=json.load(file))
                classified = classifier.classify(hit_group)
                most_likely = classifier.most_likely(classified)
                document = classified["document"]
                hit_group_class = HitGroupClass(
                        group_id=document.group_id,
                        classes=most_likely,
                        probabilities=classified["probabilities"])
                hit_group_class.save()
        except IOError:
            # We do not want make hit group details page unavailable when
            # classifier file does not exist.
            pass

    if hit_group_class is not None:
        hit_group_class_label = NaiveBayesClassifier.label(hit_group_class.classes)
    else:
        hit_group_class_label = NaiveBayesClassifier.label()

    params = {
        'multichart': False,
        'columns': HIT_DETAILS_COLUMNS,
        'title': '#Hits',
        'class': hit_group_class_label,
    }

    def hit_group_details_data_formater(input):
        for cc in input:
            yield {
                'date': cc['start_time'],
                'row': (str(cc['hits_available']),),
            }

    dicts = query_to_dicts(
                """ select start_time, hits_available from hits_mv
                    where group_id = '{}' order by start_time asc """
                .format(hit_group_id))
    data = hit_group_details_data_formater(dicts)
    params['date_from'] = hit_group.occurrence_date
    params['date_to'] = datetime.datetime.utcnow()
    params['data'] = data
    params['hit_group'] = hit_group
    return direct_to_template(request, 'main/hit_group_details.html', params)

@never_cache
def classification(request):
    data = query_to_dicts(
        """ SELECT classes, COUNT(classes) number
            FROM main_hitgroupclass
            GROUP BY classes;
        """)
    data = list(data)
    sum = 0
    for d in data:
        sum += d["number"]

    for d in data:
        d["name"] = NaiveBayesClassifier.label(d["classes"])
        d["part"] = 100 * float(d["number"]) / sum
    params = {"data":data}
    return direct_to_template(request, 'main/classification.html',
                              params)

def search(request):

    params = {}

    if request.method == 'POST' and 'query' in request.POST:
        params['query'] = request.POST['query']

    return direct_to_template(request, 'main/search.html', params)


class HitGroupContentSearchView(SearchView):

    def build_page(self):
        form = self.form
        if form is not None:
            self.results_per_page = form.hits_per_page_or_default()
        return super(HitGroupContentSearchView, self).build_page()

    def extra_context(self):
        context = super(HitGroupContentSearchView, self).extra_context()
        submit_url = ""
        form = self.form
        if form is not None:
            submit_url = form.submit_url()
        results = self.results
        if results is None:
            results = []
        context.update({"submit_url": submit_url})
        context.update({"total_count": results.count()})
        return context


@never_cache
def haystack_search(request):
    search_view = HitGroupContentSearchView(form_class=HitGroupContentSearchForm,
                                            template="main/search.html")
    return search_view(request)
