# -*- coding: utf-8 -*-

import sys

try:
    from gevent import monkey
    monkey.patch_all()
except ImportError:
    sys.exit('Gevent library is required: http://www.gevent.org/')


import time
import datetime
import logging
from optparse import make_option

import gevent
from django.core.management.base import BaseCommand

from tenclouds.pid import Pid
from crawler import tasks
from mturk.main.models import Crawl
from db import dbpool


log = logging.getLogger('crawl')


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
            make_option('--workers', dest='workers', type='int', default=3),
    )

    def setup_logging(self):
        "Basic setup for logging module"
        logging.basicConfig(filename='/tmp/mturk_crawler.log', level=logging.DEBUG)

    def handle(self, *args, **options):
        _start_time = time.time()
        self.setup_logging()
        pid = Pid('mturk_crawler', True)
        log.info('crawler started: %s;;%s', args, options)
        self.maxworkers = options['workers']
        if self.maxworkers > 9:
            # If you want to remote this limit, don't forget to change dbpool
            # object maximum number of connections. Each worker should fetch
            # 10 hitgroups and spawn single task for every one of them, that
            # will get private connection instance. So for 9 workers it's
            # already 9x10 = 90 connections required
            #
            # Also, for too many workers, amazon isn't returning valid data
            # and retrying takes much longer than using smaller amount of
            # workers
            sys.exit('Too many workers (more than 9). Quit.')
        start_time = datetime.datetime.now()

        hits_available = tasks.hits_mainpage_total()
        groups_available = tasks.hits_groups_total()

        # create crawl object that will be filled with data later
        crawl = Crawl.objects.create(
                start_time=start_time,
                end_time=datetime.datetime.now(),
                success=True,
                hits_available=hits_available,
                hits_downloaded=0,
                groups_available=groups_available,
                groups_downloaded=hits_available)
        log.debug('fresh crawl object created: %s', crawl.id)

        # manage database connections here - should be one for each
        # task working at the same time
        groups_downloaded = 0
        hitgroups_iter = self.hits_iter()
        for hg_pack in hitgroups_iter:
            groups_downloaded += len(hg_pack)
            jobs = [gevent.spawn(tasks.process_group, hg, crawl.id) for hg in hg_pack]
            log.debug('processing pack of hitgroups objects')
            gevent.joinall(jobs, timeout=15)
            # check if all jobs ended successfully
            for job in jobs:
                if not job.ready():
                    log.error('Killing job: %s', job)
                    groups_downloaded -= 1
                    job.kill(block=False)

            # amazon does not like too many requests at once, so give them a
            # quick rest...
            gevent.sleep(1)

        dbpool.closeall()

        # update crawler object
        crawl.groups_downloaded = groups_downloaded
        crawl.end_time = datetime.datetime.now()
        crawl.save()

        work_time = time.time() - _start_time
        log.info('created crawl id: %s', crawl.id)
        log.info('processed hits groups: %s/%s',
                groups_downloaded, groups_available)
        log.info('work time: %.2fsec', work_time)

    def hits_iter(self):
        """Hits group lists generator.

        As long as available, return lists of parsed hits group. Because this
        method is using concurent download, number of returned elements on
        each list cannot be greater that maximum number of workers.
        """
        counter = count(1, self.maxworkers)
        for i in counter:
            jobs =[gevent.spawn(tasks.hits_groups_info, page_nr) \
                        for page_nr in range(i, i + self.maxworkers)]
            gevent.joinall(jobs)

            # get data from completed tasks & remove empty results
            hgs = []
            for job in jobs:
                if job.value:
                    hgs.extend(job.value)

            # if no data was returned, end - previous page was probably the
            # last one with results
            if not hgs:
                break

            log.debug('yielding hits group: %s', len(hgs))
            yield hgs


def count(firstval=0, step=1):
    "Port of itertools.count from python2.7"
    while True:
        yield firstval
        firstval += step