# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 Smile (<http://www.smile.fr>).
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

from openerp import api, fields, models

from openerp.addons.smile_followers.tools import AddFollowers


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.multi
    def _get_contacts_to_notify(self):
        return self

    @api.multi
    def _get_contacts_parents(self):
        return self


@AddFollowers(['project_id.user_id.partner_id', 'project_id.members.partner_id'])
class Branch(models.Model):
    _inherit = 'scm.repository.branch'

    project_id = fields.Many2one('project.project', 'Project')


class Build(models.Model):
    _inherit = 'scm.repository.branch.build'

    @api.one
    @api.depends('result')
    def _compute_color(self):
        if self.result:
            if self.result == 'stable':
                self.color = 7  # blue
            if self.result == 'unstable':
                self.color = 3  # orange
            if self.result == 'failed':
                self.color = 2  # red
            if self.result == 'killed':
                self.color = 1  # grey

    color = fields.Integer(compute='_compute_color', readonly=True, store=False)


class ProjectProject(models.Model):
    _inherit = 'project.project'

    @api.one
    def _get_branches_count(self):
        self.branches_count = len(self.branch_ids)

    branch_ids = fields.One2many('scm.repository.branch', 'project_id', 'Branches')
    branches_count = fields.Integer('Branches Count', compute='_get_branches_count', store=False)

    @api.multi
    def _partners_to_subscribe(self):
        partners = (self.mapped('members') | self.mapped('user_id')).mapped('partner_id')
        return partners.filtered(lambda partner: 'scm.repository.branch' in partner.mapped('notification_model_ids.model'))

    @api.model
    def _message_get_auto_subscribe_fields(self, updated_fields, auto_follow_fields=None):
        "Don't add project manager as follower"
        return super(ProjectProject, self)._message_get_auto_subscribe_fields(updated_fields, ['reviewer_id'])

    @api.model
    def create(self, vals):
        record = super(ProjectProject, self).create(vals)
        if ('members' in vals or 'user_id' in vals) and 'branch_ids' in vals:
            record.branch_ids.message_subscribe(partner_ids=record._partners_to_subscribe().ids)
        return record

    @api.multi
    def write(self, vals):
        old_members = {}
        if 'members' in vals or 'user_id' in vals:
            for project in self:
                old_members[project] = project.members | project.user_id
        res = super(ProjectProject, self).write(vals)
        if 'members' in vals or 'user_id' in vals:
            for project, partners in old_members.iteritems():
                project.branch_ids.message_unsubscribe(partner_ids=partners.mapped('partner_id').ids)
                project.branch_ids.message_subscribe(partner_ids=project._partners_to_subscribe().ids)
        return res
