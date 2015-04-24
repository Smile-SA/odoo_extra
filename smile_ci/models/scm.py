# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2014 Smile (<http://www.smile.fr>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import logging
_logger = logging.getLogger(__package__)

try:
    from docker import Client
except ImportError:
    _logger.warning("Please install docker package")

from ast import literal_eval
from datetime import datetime
from dateutil.relativedelta import relativedelta
from urlparse import urljoin, urlparse

from openerp import api, models, fields, registry, tools, _
from openerp.exceptions import Warning
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT as DATETIME_FORMAT
from openerp.tools.safe_eval import safe_eval as eval

from openerp.addons.smile_scm.tools import cd

from ..tools import with_new_cursor, check_output_chain
from .build import BUILD_RESULTS

INTERVAL_TYPES = [
    ('years', 'years'),
    ('months', 'months'),
    ('weeks', 'weeks'),
    ('days', 'days'),
    ('hours', 'hours'),
    ('minutes', 'minutes'),
]


class VersionControlSystem(models.Model):
    _inherit = 'scm.vcs'

    cmd_revno = fields.Char('Get revision number', required=True)
    cmd_log = fields.Char('Get commit logs from last update', required=True)
    cmd_export = fields.Char('export remote branch')


class OdooVersion(models.Model):
    _inherit = 'scm.version'

    server_cmd = fields.Char('Server command', required=True, default='openerp-server')
    required_packages = fields.Text('Required packages', required=True)
    optional_packages = fields.Text('Optional packages')
    web_included = fields.Boolean('Web Included', default=True)
    standard_xmlrpc = fields.Boolean('Standard XML/RPC', default=True)


class OperatingSystem(models.Model):
    _name = 'scm.os'
    _description = 'Operating System'
    _order = 'name'

    name = fields.Char(required=True)
    dockerfile = fields.Binary('Dockerfile template', required=True)
    odoo_dir = fields.Char('Odoo directory', required=True, default='/usr/src/odoo')
    active = fields.Boolean(default=True)


class DockerHost(models.Model):
    _name = 'docker.host'
    _description = 'Docker Host'
    _rec_name = 'docker_base_url'

    @api.model
    def _get_default_build_base_url(self):
        base_url = self.env['ir.config_parameter'].get_param('web.base.url')
        netloc = urlparse(base_url).netloc.split(':')[0]  # Remove port
        return urljoin(base_url, '//%s' % netloc)

    docker_base_url = fields.Char(default='unix://var/run/docker.sock')
    version = fields.Char()
    timeout = fields.Integer(default=60, help='In seconds')
    tls = fields.Boolean()
    active = fields.Boolean('Active', default=True)
    redirect_subdomain_to_port = fields.Boolean()
    build_base_url = fields.Char(default=_get_default_build_base_url)

    @api.multi
    def get_client(self):
        self.ensure_one()
        kwargs = {
            'base_url': self.docker_base_url,
            'tls': self.tls,
            'timeout': self.timeout,
        }
        if self.version:
            kwargs['version'] = self.version
        return Client(**kwargs)


class Branch(models.Model):
    _inherit = 'scm.repository.branch'

    @api.model
    def _get_lang(self):
        return tools.scan_languages()

    @api.one
    def _get_last_build_result(self):
        for build in self.build_ids:  # Because builds ordered by id desc
            if build.result:
                self.last_build_result = build.result
                break
        else:
            self.last_build_result = 'unknown'

    @api.model
    def _get_default_os(self):
        return self.env['scm.os'].search([], limit=1)

    @api.one
    def _get_builds_count(self):
        self.builds_count = len(self.build_ids)

    build_ids = fields.One2many('scm.repository.branch.build', 'branch_id', 'Builds', readonly=True)
    use_in_ci = fields.Boolean('Use in Continuous Integration')
    os_id = fields.Many2one('scm.os', 'Operating System', default=_get_default_os)
    dump_id = fields.Many2one('ir.attachment', 'Dump file')
    modules_to_install = fields.Text('Modules to install')
    install_demo_data = fields.Boolean(default=True, help='If checked, demo data will be installed')
    ignored_tests = fields.Text('Tests to ignore', help="Example: {'account': ['test/account_bank_statement.yml'], 'sale': 'all'}")
    server_path = fields.Char('Server path', default="server")
    addons_path = fields.Text('Addons path', default="addons", help="Comma-separated")
    code_path = fields.Text('Source code to analyse path', help="Addons path for which checking code quality and coverage.\n"
                                                                "If empty, all source code is checked.")
    test_path = fields.Text('Addons path to test', help="Exclusively run tests of modules defined inside these paths.\n"
                                                        "If empty, all modules installed will be tested.")
    workers = fields.Integer('Workers', default=0, required=True)
    user_uid = fields.Integer('Admin id', default=1, required=True)
    user_passwd = fields.Char('Admin password', default='admin', required=True)
    lang = fields.Selection('_get_lang', 'Language', default='en_US', required=True)
    last_build_result = fields.Selection(BUILD_RESULTS + [('unknown', 'Unknown')], 'Last result',
                                         compute='_get_last_build_result', store=False)
    builds_count = fields.Integer('Builds Count', compute='_get_builds_count', store=False)
    subfolder = fields.Char('Place current sources in')
    merge_with_branch_id = fields.Many2one('scm.repository.branch', 'Merge with')
    merge_subfolder = fields.Char('Place merged sources in')
    specific_packages = fields.Text('Specific packages')
    pip_packages = fields.Text('PIP requirements')
    additional_options = fields.Text('Additional configuration options')

    nextcall = fields.Datetime(required=True, default=fields.Datetime.now())
    interval_number = fields.Integer('Interval Number', help="Repeat every x.", required=True, default=15)
    interval_type = fields.Selection(INTERVAL_TYPES, 'Interval Unit', required=True, default='minutes')

    @api.onchange('merge_with_branch_id')
    def _onchange_merge_with_branch_id(self):
        if not self.merge_with_branch_id:
            self.merge_subfolder = ''
            self.subfolder = ''

    @api.one
    @api.constrains('use_in_ci', 'os_id')
    def _check_os_id(self):
        if self.use_in_ci and not self.os_id:
            raise Warning(_('Operating System is mandatory is branch is used in CI'))

    @api.one
    @api.constrains('ignored_tests')
    def _check_ignored_tests(self):
        if not self.ignored_tests:
            return
        if type(eval(self.ignored_tests)) != dict:
            raise Warning(_("Please use a dict"))
        message = "Values must be of type: str, unicode or list of str / unicode"
        for value in eval(self.ignored_tests).values():
            if type(value) == list:
                if filter(lambda element: type(element) not in (str, unicode), value):
                    raise Warning(_(message))
            elif type(value) not in (str, unicode):
                raise Warning(_(message))

    @api.one
    def _update(self):
        if self.state == 'draft':
            self.clone()
        else:
            self.pull()
        nextcall = datetime.strptime(fields.Datetime.now(), DATETIME_FORMAT)
        nextcall += relativedelta(**{self.interval_type: self.interval_number})
        self.nextcall = nextcall.strftime(DATETIME_FORMAT)

    @api.multi
    def _get_revno(self):
        self.ensure_one()
        revno = ''
        with cd(self.directory):
            vcs = self.vcs_id
            cmd_revno = vcs.cmd_revno % {'branch': self.branch}
            cmd = cmd_revno.split(' ')
            cmd.insert(0, vcs.cmd)
            revno = check_output_chain(cmd)
            if vcs.name == 'Subversion':
                revno = revno.split(' ')[0]
            elif vcs.name != 'Git':
                revno = literal_eval(revno)
            return revno.replace('\n', '')

    @api.multi
    def _get_last_commits(self):
        self.ensure_one()
        last_commits = ''
        with cd(self.directory):
            vcs = self.vcs_id
            last_revno = self.build_ids and self.build_ids[0].revno.encode('utf8') or self._get_revno()
            cmd_log = vcs.cmd_log % {'last_revno': last_revno}
            cmd = cmd_log.split(' ')
            cmd.insert(0, vcs.cmd)
            last_commits = check_output_chain(cmd)
        return last_commits

    @api.multi
    def _changes(self):
        self.ensure_one()
        if not self.build_ids or tools.ustr(self._get_revno()) != tools.ustr(self.build_ids[0].revno):  # Because builds ordered by id desc
            return True
        return False

    @api.one
    def create_build(self, force=False):
        self._create_build(force)
        return True

    @api.multi
    @with_new_cursor()
    def _create_build(self, force=False):
        self.ensure_one()
        self._try_lock(_('Build Creation already in progress'))
        if self.use_in_ci:
            self._update()
            if self._changes() or force is True:
                self.merge_with_branch_id._update()
                vals = {'branch_id': self.id, 'revno': self._get_revno(), 'commit_logs': self._get_last_commits()}
                self.env['scm.repository.branch.build'].create(vals)

    @api.multi
    def force_create_build(self):
        self.create_build(force=True)
        return True

    @api.model
    def _force_create_build_with_new_cursor(self, branch_ids):
        with api.Environment.manage():
            with registry(self._cr.dbname).cursor() as new_cr:
                try:
                    self.with_env(self.env(cr=new_cr)).browse(branch_ids).force_create_build()
                except Exception, e:
                    _logger.error(repr(e))
                    new_cr.rollback()

    @api.model
    def create_builds(self):
        """Method called by a scheduled action executed each X-minutes"""
        branches = self.search([('use_in_ci', '=', True), ('nextcall', '<=', fields.Datetime.now())])
        branches.create_build()
        return True

    @api.model
    def _get_purge_date(self, age_number, age_type):
        assert isinstance(age_number, (int, long))
        assert age_type in ('years', 'months', 'weeks', 'days', 'hours', 'minutes', 'seconds')
        last_creation_date = self.build_ids and self.build_ids[0].create_date
        date = datetime.strptime(last_creation_date, DATETIME_FORMAT) + relativedelta(**{age_type: -age_number})
        return date.strftime(DATETIME_FORMAT)

    @api.one
    def _purge_builds(self, age_number, age_type):
        date = self._get_purge_date(age_number, age_type)
        _logger.info('Purging builds created before %s for %s %s...' % (date, self.repository_id.name, self.branch))
        self.env['scm.repository.branch.build'].purge(date)

    @api.model
    def purge_builds(self, age_number=6, age_type='months'):
        """
        For each branch, get the last creation date of a build 
        then remove builds older than this date minus [age_number age_type].

        @param age_number, integer: number of time
        @param age_type, integer: unit of time
        @return: True
        """
        for branch in self.search([]):
            branch._purge_builds(age_number, age_type)
        return True
