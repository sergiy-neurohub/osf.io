# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2017-04-04 03:28
from __future__ import unicode_literals

from django.db import migrations
import osf.utils.fields


class Migration(migrations.Migration):

    dependencies = [
        ('addons_wiki', '0002_auto_20170323_1534'),
    ]

    operations = [
        migrations.AlterField(
            model_name='nodewikipage',
            name='date',
            field=osf.utils.fields.NonNaiveDateTimeField(auto_now_add=True),
        ),
    ]