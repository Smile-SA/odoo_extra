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

{
    "name": "Continuous Integration - Project Management",
    "version": "0.1",
    "depends": [
        "smile_ci",
        "smile_followers",
        "project",
    ],
    "author": "Smile",
    "description": """
Continuous Integration - Project Management

Suggestions & Feedback to: corentin.pouhet-brunerie@smile.fr & isabelle.richard@smile.fr
    """,
    "summary": "Manage projects by team",
    "website": "http://www.smile.fr",
    "category": 'Tools',
    "sequence": 20,
    "data": [
        # Security
        "security/scm_security.xml",

        # Views
        "views/scm_repository_view.xml",
        "views/project_view.xml",
    ],
    "demo": [],
    "auto_install": False,
    "installable": True,
    "application": False,
}
