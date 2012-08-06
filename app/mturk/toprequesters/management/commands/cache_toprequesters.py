import time
import logging
from django.core.cache import cache
from utils.pid import Pid

from django.core.management.base import BaseCommand, NoArgsCommand
from optparse import make_option
from mturk.toprequesters.reports import ToprequestersReport

HOURS4 = 60 * 60 * 4

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Command for populating toprequesters reports into cache.

    Allows the user to see available reports and their status, cache all or
    selected reports.

    """

    option_list = NoArgsCommand.option_list + (
        make_option('--days', dest='days', default='30',
            help='Number of days from which the history data is grabbed.'),
        make_option('--force', dest='force', action="store_true", default=False,
            help='Enforces overriding existing entry in the cache.'),
        make_option('--all', dest='all', action="store_true", default=False,
            help='Evaluates all reports available.'),
        make_option('--list', dest='list', action="store_true", default=False,
            help='Shows a list of available report types.'),
        make_option('--report-type', dest='report-type', type="int",
            default=ToprequestersReport.AVAILABLE,
            help='The report to rebuild.'),

    )
    help = 'Make sure top requesters are in cache.'

    def handle(self, **options):
        """Main command entry point."""

        pid = Pid('mturk_cache_topreq', True)

        self.options = options
        report_type = options.get('report-type')

        if self.handle_list():
            pass
        elif report_type not in ToprequestersReport.values:
            log.info('Unknown report type: "{0}".'.format(report_type))
        else:
            reports = (ToprequestersReport.values if options['all'] else
                      [report_type])
            log.info('Caching reports: {0}.'.format(reports))
            for report_type in reports:
                self.__cache_report(report_type)

        pid.remove_pid()

    def __cache_report(self, report_type):
        """Evaluates the report and stores it under correct cache key."""

        key = ToprequestersReport.get_cache_key(report_type)
        display_name = ToprequestersReport.display_names[report_type]

        if ToprequestersReport.is_cached(report_type):
            if self.options['force']:
                log.info('Recalculating "{0}" toprequesters report.'.format(
                    display_name))
            else:
                log.info('"{0}" toprequesters still in cache, use --force flag'
                    ' to rebuild anyway.'.format(display_name))
                return False
        else:
            log.info(('"{0}" toprequesters report missing, recalculating.'
                ).format(display_name))

        start_time = time.time()

        days = self.options['days']
        data = ToprequestersReport.REPORT_FUNCTION[report_type](days)
        log.info('Toprequesters report "{0}" generated in: {1}s.'.format(
            display_name, time.time() - start_time))

        # too often we get no information on the success of caching
        if not data:
            log.warning('Data returned by report function is {0}!'.format(data))
        else:
            ToprequestersReport.store(report_type, data)
            cache.set(key, data, HOURS4)
            in_cache = cache.get(key, data)
            if in_cache is None:
                log.warning('Cache error - data could not be fetched!')
        return True

    def handle_list(self):
        """Shows available report types: id - name and returns boolean
        determining if this option is available in cache.

        """
        if self.options['list']:
            print ("Available report types: \n" +
                ToprequestersReport.get_available_str())
        return self.options['list']
