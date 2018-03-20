# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-02-22 20:39
from __future__ import unicode_literals

import gc
import logging
import progressbar
from django.db import connection, migrations
from django.db.models import Q
from osf.utils.migrations import disable_auto_now_add_fields
from django.contrib.contenttypes.models import ContentType
from addons.wiki.models import WikiPage, NodeWikiPage, WikiVersion
from osf.models import Comment, Guid, AbstractNode
from bulk_update.helper import bulk_update

logger = logging.getLogger(__name__)

# Cache of WikiPage id => guid, of the form
# {
#     <id>: <guid_pk>
#
# }
WIKI_PAGE_GUIDS = {}

def reverse_func(state, schema):
    """
    Reverses NodeWikiPage migration. Repoints guids back to each NodeWikiPage,
    repoints comment_targets, comments_viewed_timestamps, and deletes all WikiVersions and WikiPages
    """
    nwp_content_type_id = ContentType.objects.get_for_model(NodeWikiPage).id

    nodes = AbstractNode.objects.exclude(wiki_pages_versions={})
    progress_bar = progressbar.ProgressBar(maxval=nodes.count()).start()
    for i, node in enumerate(nodes, 1):
        progress_bar.update(i)
        for wiki_key, version_list in node.wiki_pages_versions.iteritems():
            if version_list:
                for index, version in enumerate(version_list):
                    nwp = NodeWikiPage.objects.filter(former_guid=version).include(None)[0]
                    wp = WikiPage.load(version)
                    guid = migrate_guid_referent(Guid.load(version), nwp, nwp_content_type_id)
                    guid.save()
                    nwp = guid.referent
                move_comment_target(Guid.load(wp._id), wp, nwp)
                update_comments_viewed_timestamp(node, wp, nwp)
    progress_bar.finish()
    WikiVersion.objects.all().delete()
    WikiPage.objects.all().delete()
    logger.info('NodeWikiPages restored and WikiVersions and WikiPages removed.')

def move_comment_target(current_guid, current_target, desired_target):
    """Move the comment's target from the current target to the desired target"""
    desired_target_guid_id = WIKI_PAGE_GUIDS[desired_target.id]
    if Comment.objects.filter(Q(root_target=current_guid) | Q(target=current_guid)).exists():
        Comment.objects.filter(root_target=current_guid).update(root_target_id=desired_target_guid_id)
        Comment.objects.filter(target=current_guid).update(target_id=desired_target_guid_id)
    return

def update_comments_viewed_timestamp(node, current_wiki_guid, desired_wiki_object):
    """Replace the current_wiki_object keys in the comments_viewed_timestamp dict with the desired wiki_object_id """
    users_pending_save = []
    # We iterate over .contributor_set instead of .contributors in order
    # to take advantage of .include('contributor__user')
    for contrib in node.contributor_set.all():
        user = contrib.user
        if user.comments_viewed_timestamp.get(current_wiki_guid, None):
            timestamp = user.comments_viewed_timestamp[current_wiki_guid]
            user.comments_viewed_timestamp[desired_wiki_object._id] = timestamp
            del user.comments_viewed_timestamp[current_wiki_guid]
            users_pending_save.append(user)
    if users_pending_save:
        bulk_update(users_pending_save, update_fields=['comments_viewed_timestamp'])
    return users_pending_save

def migrate_guid_referent(guid, desired_referent, content_type_id):
    """
    Point the guid towards the desired_referent.
    Pointing the NodeWikiPage guid towards the WikiPage will still allow links to work.
    """
    guid.content_type_id = content_type_id
    guid.object_id = desired_referent.id
    return guid

# def create_wiki_page(node, node_wiki, page_name):
#     wp = WikiPage(
#         page_name=page_name,
#         user_id=node_wiki.user_id,
#         node=node,
#         created=node_wiki.date,
#             modified=node_wiki.modified,
#     )
#     wp.update_modified = False
#     return wp


def create_wiki_pages_sql(state, schema):
    logger.info('Starting migration of WikiPages [SQL]:')
    wikipage_content_type_id = ContentType.objects.get_for_model(WikiPage).id
    nodewikipage_content_type_id = ContentType.objects.get_for_model(NodeWikiPage).id
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TEMPORARY TABLE temp_wikipages
            (
              node_id INTEGER,
              user_id INTEGER,
              page_name_key TEXT,
              page_name_guid TEXT,
              page_name_display TEXT,
              created TIMESTAMP,
              modified TIMESTAMP
            )
            ON COMMIT DROP;

            -- Flatten out the wiki_page_versions json keys
            INSERT INTO temp_wikipages (node_id, page_name_key)
            SELECT
              oan.id AS node_id
              , jsonb_object_keys(oan.wiki_pages_versions) as page_name_key
            FROM osf_abstractnode AS oan;

            -- Retrieve the latest guid for the json key
            UPDATE temp_wikipages AS twp
            SET
              page_name_guid = (
                  SELECT trim(v::text, '"')
                  FROM osf_abstractnode ioan
                    , jsonb_array_elements(oan.wiki_pages_versions->twp.page_name_key) WITH ORDINALITY v(v, rn)
                  WHERE ioan.id = oan.id
                  ORDER BY v.rn DESC
                  LIMIT 1
              )
            FROM osf_abstractnode AS oan
            WHERE oan.id = twp.node_id;

            -- Remove any json keys that reference empty arrays (bad data? e.g. abstract_node id=232092)
            DELETE FROM temp_wikipages AS twp
            WHERE twp.page_name_guid IS NULL;

            -- Retrieve nodewikipage fields for the wiki page guid
            UPDATE temp_wikipages AS twp
            SET
              user_id = anwp.user_id
              , page_name_display = anwp.page_name
              , created = anwp.created
              , modified = anwp.modified
            FROM osf_guid AS og INNER JOIN addons_wiki_nodewikipage AS anwp ON (og.object_id = anwp.id AND og.content_type_id = %s)
            WHERE og._id = twp.page_name_guid;

            -- Populate the wikipage table
            INSERT INTO addons_wiki_wikipage (node_id, user_id, content_type_pk, page_name, created, modified)
            SELECT
              twp.node_id
              , twp.user_id
              , %s
              , twp.page_name_display
              , twp.created
              , twp.modified
            FROM temp_wikipages AS twp;
            """, [nodewikipage_content_type_id, wikipage_content_type_id]
        )
    logger.info('Finished migration of WikiPages [SQL]:')

def create_wiki_version(node_wiki, wiki_page):
    wv = WikiVersion(
        wiki_page=wiki_page,
        user_id=node_wiki.user_id,
        created=node_wiki.date,
        modified=node_wiki.modified,
        content=node_wiki.content,
        identifier=node_wiki.version,
    )
    wv.update_modified = False
    return wv

def create_guids(state, schema):
    global WIKI_PAGE_GUIDS
    content_type = ContentType.objects.get_for_model(WikiPage)
    progress_bar = progressbar.ProgressBar(maxval=WikiPage.objects.count()).start()
    logger.info('Creating new guids for all WikiPages:')
    for i, wiki_page_id in enumerate(WikiPage.objects.values_list('id', flat=True), 1):
        # looping instead of bulk_create, so _id's are not the same
        progress_bar.update(i)
        guid = Guid.objects.create(object_id=wiki_page_id, content_type_id=content_type.id)
        WIKI_PAGE_GUIDS[wiki_page_id] = guid.id
    progress_bar.finish()
    logger.info('WikiPage guids created.')
    return

# def create_wiki_pages(nodes):
#     wiki_pages = []
#     progress_bar = progressbar.ProgressBar(maxval=len(nodes)).start()
#     logger.info('Starting migration of WikiPages:')
#     for i, node in enumerate(nodes, 1):
#         progress_bar.update(i)
#         for wiki_key, version_list in node.wiki_pages_versions.iteritems():
#             if version_list:
#                 node_wiki = NodeWikiPage.objects.filter(former_guid=version_list[0]).only('user_id', 'date', 'modified').include(None)[0]
#                 latest_page_name = NodeWikiPage.objects.filter(former_guid=version_list[-1]).values_list('page_name', flat=True).include(None)[0]
#                 wiki_pages.append(create_wiki_page(node, node_wiki, latest_page_name))
#         if len(wiki_pages) >= 1000:
#             with disable_auto_now_add_fields(models=[WikiPage]):
#                 WikiPage.objects.bulk_create(wiki_pages, batch_size=1000)
#                 wiki_pages = []
#             gc.collect()
#     progress_bar.finish()
#     # Create the remaining wiki pages that weren't created in the loop above
#     with disable_auto_now_add_fields(models=[WikiPage]):
#         WikiPage.objects.bulk_create(wiki_pages, batch_size=1000)
#     logger.info('WikiPages saved.')
#     return

def create_wiki_versions(nodes):
    wp_content_type_id = ContentType.objects.get_for_model(WikiPage).id
    wiki_versions_pending = []
    guids_pending = []
    progress_bar = progressbar.ProgressBar(maxval=len(nodes)).start()
    logger.info('Starting migration of WikiVersions:')
    for i, node in enumerate(nodes, 1):
        progress_bar.update(i)
        for wiki_key, version_list in node.wiki_pages_versions.iteritems():
            if version_list:
                node_wiki_guid = version_list[0]
                node_wiki = NodeWikiPage.objects.filter(former_guid=node_wiki_guid).include(None)[0]
                page_name = NodeWikiPage.objects.filter(former_guid=version_list[-1]).values_list('page_name', flat=True).include(None)[0]
                wiki_page = node.wikis.get(page_name=page_name)
                for index, version in enumerate(version_list):
                    if index:
                        node_wiki = NodeWikiPage.objects.filter(former_guid=version).include(None)[0]
                    wiki_versions_pending.append(create_wiki_version(node_wiki, wiki_page))
                    current_guid = Guid.load(version)
                    guids_pending.append(migrate_guid_referent(current_guid, wiki_page, wp_content_type_id))
                move_comment_target(current_guid, node_wiki_guid, wiki_page)
                update_comments_viewed_timestamp(node, node_wiki_guid, wiki_page)
        if len(wiki_versions_pending) >= 1000:
            with disable_auto_now_add_fields(models=[WikiVersion]):
                WikiVersion.objects.bulk_create(wiki_versions_pending, batch_size=1000)
                wiki_versions_pending = []
                gc.collect()
        if len(guids_pending) > 1000:
            bulk_update(guids_pending, update_fields=['content_type_id', 'object_id'], batch_size=100)
            guids_pending = []
            gc.collect()
    progress_bar.finish()
    # Create the remaining wiki pages that weren't created in the loop above
    with disable_auto_now_add_fields(models=[WikiVersion]):
        WikiVersion.objects.bulk_create(wiki_versions_pending, batch_size=1000)
    bulk_update(guids_pending, update_fields=['content_type_id', 'object_id'], batch_size=100)
    logger.info('WikiVersions saved.')
    logger.info('Repointed NodeWikiPage guids to corresponding WikiPage')
    return

# def migrate_node_wiki_pages(state, schema):
#     """
#     For every node, loop through all the NodeWikiPages on node.wiki_pages_versions.  Create a WikiPage, and then a WikiVersion corresponding
#     to each WikiPage.
#         - Loads all nodes with wikis on them.
#         - For each node, loops through all the keys in wiki_pages_versions.
#         - Creates all wiki pages and then bulk creates them, for speed.
#         - For all wiki pages that were just created, create and save a guid (since bulk_create doesn't call save method)
#         - Loops through all nodes again, creating a WikiVersion for every guid for all wiki pages on a node.
#         - Repoints guids from old wiki to new WikiPage
#         - For the most recent version of the WikiPage, repoint comments to the new WikiPage
#         - For comments_viewed_timestamp that point to the NodeWikiPage, repoint to the new WikiPage
#     """
#     nodes_with_wikis = (
#         AbstractNode.objects
#         .exclude(wiki_pages_versions={})
#         .exclude(type='osf.collection')
#         .exclude(type='osf.quickfilesnode')
#         # .include(None) removes GUID prefetching--we don't need that. But we do prefetch contributors
#         .include(None)
#         .include('contributor__user')
#     )
#     for nodes in grouper(100, nodes_with_wikis):
#         create_wiki_pages(nodes)
#
#     create_guids()
#
#     for nodes in grouper(100, nodes_with_wikis):
#         create_wiki_versions(nodes)


class Migration(migrations.Migration):

    dependencies = [
        ('addons_wiki', '0009_auto_20180302_1404'),
    ]

    operations = [
        migrations.RunPython(create_wiki_pages_sql, reverse_func),
        migrations.RunPython(create_guids, reverse_func)
        # migrations.RunPython(create_wiki_versions_sql, reverse_func),
    ]


# # Iterate an iterator by chunks (of n) in Python?
# # source: https://stackoverflow.com/a/8991553
# import itertools
# def grouper(n, iterable):
#     if hasattr(iterable, 'iterator'):
#         it = iterable.iterator()
#     else:
#         it = iter(iterable)
#     while True:
#        chunk = tuple(itertools.islice(it, n))
#        if not chunk:
#            return
#        yield chunk
