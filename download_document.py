import datetime
from itertools import islice
import json
import xml.etree.ElementTree as ET
import logging
import re
import urllib2
import werkzeug.utils
import werkzeug.wrappers

import odoo
from odoo import http
from odoo import fields
from odoo.http import request
from odoo.osv.orm import browse_record

from odoo.addons.website.models.website import slug
from odoo.addons.web.controllers.main import WebClient, Binary, Home

import base64
import pyPdf

logger = logging.getLogger(__name__)


def binary_content(xmlid=None, model='ir.attachment', id=None, field='datas', unique=False, filename=None, filename_field='datas_fname', download=False, mimetype=None, default_mimetype='application/octet-stream', env=None):
    return request.registry['ir.http'].binary_content(
        xmlid=xmlid, model=model, id=id, field=field, unique=unique, filename=filename, filename_field=filename_field,
        download=download, mimetype=mimetype, default_mimetype=default_mimetype, env=env)  
    
def find_publish_paper(pub_id, journal_id, publish_paper_lists, is_first_record):
    authors = None; ir_attachement_id = None;type_of_artcile = 'N/A'
    for record in pub_id.documents_ids:
        if record.check_journal == True:
            convert_title = record.title.encode("utf-8")
            for upload_document_id in request.env['upload.document'].sudo().search([('name','=', convert_title),('company_id','=',journal_id.id), ('state','in',['accepted','published'])]):
                if upload_document_id.article_type:
                    if upload_document_id.article_type == 'research_paper':
                        type_of_artcile = 'Research Paper'
                    elif upload_document_id.article_type == 'review_article':
                        type_of_artcile = 'Review Article'
                    elif upload_document_id.article_type == 'short_comm':
                        type_of_artcile = 'Short Communication'
                if upload_document_id.authors:
                     authors= upload_document_id.authors
                for attachement_id in upload_document_id.final_doc_ids:
                    ir_attachement_id = attachement_id.id
                publish_paper_lists.append({'name': record.title,'author_id': authors, 'type_of_artcile':type_of_artcile, 'page':upload_document_id.page_no,
                                            'article_info':upload_document_id.article_info, 'journal_name': upload_document_id.journal_name, 'ir_attachement_id':ir_attachement_id})
            is_first_record = True
    return publish_paper_lists, is_first_record

class Website(Home):
    
    @http.route('/shc/publish_paper/', type='http', auth="public", methods=['GET', 'POST'], website=True)
    def publishpaper(self, **form_data):
        values = {}; publish_paper_list = []; volume_list = []; publish_paper_lists = []; title = ''; convert_title = ''; ir_attachement_id = None; type_of_artcile = None;
        authors = None; vol_no = None
        if 'name'  in form_data:
            is_first_record = False; issn_no = ''
            journal_id = request.env['res.company'].sudo().search([('name','like',form_data['name'])])
            # Append the name as desc
            for record in request.env['publish.document'].sudo().search([('company_id','=',journal_id.id)], order="id desc"):
                if record.name:
                    volume_list.append({'volume_name': record.name})
            for volume in volume_list:
                if is_first_record == False:
                    vol_no = volume['volume_name']
                    issn_no = journal_id.issn_no
                    for article in request.env['publish.document'].sudo().search([('name', '=', volume['volume_name'])]):
                        publish_paper_lists, is_first_record = find_publish_paper(article, journal_id, publish_paper_lists, is_first_record)
                    volume_id = request.env['publish.document'].sudo().search([('name', '=', volume['volume_name'])])
                    if volume_id:
                        for publish_doc_id in request.env['publish.document'].sudo().search([('volume_id', '=', volume_id.id)],order="id desc"):
                            publish_paper_list, is_first_record = find_publish_paper(publish_doc_id, journal_id , publish_paper_list , is_first_record)
                    for rec in publish_paper_lists:
                        publish_paper_list.append({'name': rec['name'],'author_id': rec['author_id'], 'type_of_artcile':rec['type_of_artcile'], 'page':rec['page'],
                                                   'article_info':rec['article_info'], 'journal_name': rec['journal_name'],'ir_attachement_id': rec['ir_attachement_id']})
            values = {'papers': publish_paper_list, 'volume_name':vol_no, 'issn_no':issn_no, 'volumes':volume_list}
        elif 'volume' in form_data:
            is_first_record = False; type_of_artcile = None; issn_no = ''
            pub_document_id = request.env['publish.document'].sudo().search([('name','=',form_data['volume'])], order="id desc")
            if pub_document_id:
                 publish_paper_lists, is_first_record = find_publish_paper(pub_document_id, pub_document_id.company_id, publish_paper_lists, is_first_record)
            for publish_line_id in request.env['publish.document'].sudo().search([('company_id','=',pub_document_id.company_id.id), ('volume_id', '=', pub_document_id.id)], order="id desc"):
                publish_paper_list, is_first_record = find_publish_paper(publish_line_id, pub_document_id.company_id, publish_paper_list, is_first_record)
            for pub_id in request.env['publish.document'].sudo().search([('company_id','=',pub_document_id.company_id.id)], order="id desc"):
                if pub_id.name:
                    volume_list.append({'volume_name': pub_id.name})
            for rec in publish_paper_lists:
                publish_paper_list.append({'name': rec['name'],'author_id': rec['author_id'], 'type_of_artcile':rec['type_of_artcile'], 'page':rec['page'],
                                           'article_info':rec['article_info'], 'journal_name': rec['journal_name'], 'ir_attachement_id': rec['ir_attachement_id']})
            if pub_document_id.company_id.issn_no:
                issn_no = pub_document_id.company_id.issn_no
            values = {'papers': publish_paper_list, 'volumes':volume_list,
                      'volume_name': pub_document_id.name, 'issn_no':issn_no, 'start_page':pub_document_id.from_page_no, 'end_page':pub_document_id.to_page_no}
            
        elif 'search'  in form_data:
            is_first_record = False; count = 0; type_of_article = None; authors_name = None
            if form_data['search']:
                publish_document_id = request.env['publish.document'].sudo().search([('name','like',form_data['search'])])
                publish_document_id1 = request.env['publish.document'].sudo().search([('volume_id.name', '=', form_data['search'])])
                upload_document_id = request.env['upload.document'].sudo().search([('name','like',form_data['search'])])
                res_user_id = request.env['res.users'].sudo().search([('name','ilike',form_data['search'])], limit=1)
                if publish_document_id:
                    publish_paper_list, is_first_record = find_publish_paper(publish_document_id, publish_document_id.company_id, publish_paper_list, is_first_record)
                    volume_list.append({'volume_name': publish_document_id.name})
                    if publish_document_id1:
                        for pub_doc_id in publish_document_id1:
                            publish_paper_lists, is_first_record = find_publish_paper(pub_doc_id, pub_doc_id.company_id, publish_paper_lists, is_first_record)
                        for rec in publish_paper_lists:
                            publish_paper_list.append({'name': rec['name'],'author_id': rec['author_id'], 'type_of_artcile':rec['type_of_artcile'], 'page':rec['page'],
                                                       'article_info':rec['article_info'], 'journal_name': rec['journal_name'], 'ir_attachement_id': rec['ir_attachement_id']})
                elif upload_document_id:
                    if upload_document_id.article_type:
                        if upload_document_id.article_type == 'research_paper':
                            type_of_artcile = 'Research Paper'
                        elif upload_document_id.article_type == 'review_article':
                            type_of_artcile = 'Review Article'
                        elif upload_document_id.article_type == 'short_comm':
                            type_of_artcile = 'Short Communication'
                    pub_line_id = request.env['published.line'].sudo().search([('title','like',form_data['search'])], limit=1,  order="id asc")
                    if pub_line_id:
                        if pub_line_id.published_document_id.name:
                            volume_list.append({'volume_name': pub_line_id.published_document_id.name})
                        else:
                             volume_list.append({'volume_name': pub_line_id.published_document_id.volume_id.name})
                        if is_first_record == False:
                            if upload_document_id.author_id:
                                authors_name = upload_document_id.author_id.name
                                for ir_attachement_id in upload_document_id.final_doc_ids:
                                        ir_attachement_id = ir_attachement_id.id
                                publish_paper_list.append({'name': pub_line_id.title,'author_id': authors_name, 'page':upload_document_id.page_no, 'type_of_artcile':type_of_artcile, 'article_info':upload_document_id.article_info,
                                                            'journal_name': upload_document_id.journal_name,'ir_attachement_id':ir_attachement_id})
                            is_first_record = True
                elif res_user_id:
                    volume_name = ''
                    for pub_id in request.env['upload.document'].sudo().search([('author_id','=', res_user_id.id)]):
                        if pub_id.article_type:
                            if pub_id.article_type == 'research_paper':
                                type_of_artcile = 'Research Paper'
                            elif pub_id.article_type == 'review_article':
                                type_of_artcile = 'Review Article'
                            elif pub_id.article_type == 'short_comm':
                                type_of_artcile = 'Short Communication'
                        pub_line_id = request.env['published.line'].sudo().search([('title','like',pub_id.name)], limit=1)
                        if pub_line_id:
                            volume_name = pub_line_id.published_document_id.name
                            if is_first_record == False:
                                if pub_id.author_id:
                                    authors_name = pub_id.author_id.name
                                for ir_attachement_id in pub_id.final_doc_ids:
                                        ir_attachement_id = ir_attachement_id.id
                                publish_paper_list.append({'name': pub_line_id.title,'author_id': authors_name, 'page':pub_id.page_no, 'type_of_artcile':type_of_artcile, 
                                                           'article_info':pub_id.article_info, 'journal_name': pub_id.journal_name, 'ir_attachement_id':ir_attachement_id})
                                is_first_record = True
                    if volume_name:
                        volume_list.append({'volume_name': volume_name})
            values = {'papers': publish_paper_list, 'volumes':volume_list}
        return request.render("shc_published_paper.publish_paper", values)
    
    @http.route(['/abstract_paper/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def abstractpaper(self, **form_data):
        values = {}; publish_paper_list = []; ir_attachement_id = None; authors = None; author_affiliation1 = None; volume = None
        author_affiliation5 = None; author_affiliation4 = None; author_affiliation3 = None; author_affiliation2 = None;publish_date = None; date=None
    #         print form_data['paper'].encode("utf-8")
        is_jlogo_or_notes = False; type_of_artcile = None
        upload_document_ids = request.env['upload.document'].sudo().search([('name','=',form_data['paper'])])
        
        pub_line_id = request.env['published.line'].sudo().search([('title','=',form_data['paper'])], limit=1)
        for pub_id in upload_document_ids:
            if pub_id.article_type:
                if pub_id.article_type == 'research_paper':
                    type_of_artcile = 'Research Paper'
                elif pub_id.article_type == 'review_article':
                    type_of_artcile = 'Review Article'
                elif pub_id.article_type == 'short_comm':
                    type_of_artcile = 'Short Communication'
            if pub_id.company_id.name or pub_id.published_logo:
               is_jlogo_or_notes = True
            # Combine authors details with comma
            if pub_id.authors:
                    authors= pub_id.authors
            if pub_id.author_affiliation1:
                author_affiliation1 = pub_id.author_affiliation1
            elif pub_id.author_id.partner_id.college:
                author_affiliation1 = pub_id.author_id.partner_id.college
            if pub_id.author_affiliation2:
                author_affiliation2 = pub_id.author_affiliation2
            if pub_id.author_affiliation3:
                 author_affiliation3 = pub_id.author_affiliation3
            if pub_id.author_affiliation4:
                 author_affiliation4 = pub_id.author_affiliation4
            if pub_id.author_affiliation5:
                 author_affiliation5 = pub_id.author_affiliation5
            if pub_id.state_update_on:
                from datetime import datetime
                publish_date = datetime.strptime(str(pub_id.state_update_on), '%Y-%m-%d %H:%M:%S').date()
                if publish_date:
                    date = publish_date.strftime('%B %d, %Y')
            if pub_line_id.published_document_id.name:
                volume = pub_line_id.published_document_id.name
            elif pub_line_id.published_document_id.volume_id:
                volume = pub_line_id.published_document_id.volume_id.name
            publish_paper_list.append({'abstract':pub_id.abstract, 'volume':volume,'title':pub_id.name,
                                       'page':pub_id.page_no,'volume1':volume, 'author_id':authors,
                                       'affiliation1': author_affiliation1, 'affiliation2':author_affiliation2, 'affiliation3':author_affiliation3,
                                       'affiliation4':author_affiliation4, 'affiliation5':author_affiliation5, 'type_of_artcile':type_of_artcile,
                                       'keywords':pub_id.keywords, 'doi':pub_id.journal_name, 'publish_date':date,
                                       'journal_notes':pub_id.company_id.name, 'jlogo':pub_id.published_logo, 'is_jlogo_or_notes':is_jlogo_or_notes})
        for pub_id in upload_document_ids:
            for ir_attachement_id in pub_id.final_doc_ids:
                if ir_attachement_id:
                    ir_attachement_id = ir_attachement_id.id
        values = {'papers': publish_paper_list, 'ir_attachement_id':ir_attachement_id}
        return request.render("shc_published_paper.abstract_paper", values)
    
    @http.route(['/shc/journals/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def journals(self, **form_data):
        values={}
        return request.render("shc_published_paper.journals", values)
    
    @http.route(['/shc/articles/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def articles(self, **form_data):
        values={}
        return request.render("shc_published_paper.articles", values)
    
    # Computer Journal
    @http.route(['/computing_home/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def computing_guidelines(self, **form_data):
        values = {}; 
        return request.render("shc_published_paper.computing_home", values)
    
    @http.route(['/computing_guidelines/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def computing_guidelines_rules(self, **form_data):
        values = {}; 
        return request.render("shc_published_paper.computing_guidelines", values)

    @http.route(['/editorial_board/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def editorial_board(self, **form_data):
        values = {}; 
        return request.render("shc_published_paper.editorial_board", values)
    
    # Maths Journal
    @http.route(['/maths_home/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def maths_home(self, **form_data):
        values = {}; 
        return request.render("shc_published_paper.maths_home", values)
    
    @http.route(['/maths_guidelines/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def maths_guidelines(self, **form_data):
        values = {}; 
        return request.render("shc_published_paper.maths_guidelines", values)
    
    @http.route(['/maths_editorial/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def maths_editorial(self, **form_data):
        values = {}; 
        return request.render("shc_published_paper.maths_editorial", values)
    
    @http.route(['/materials_home/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def materials_home(self, **form_data):
        values = {}; 
        return request.render("shc_published_paper.materials_home", values)
    
    # Material Journal
    @http.route(['/materials_guidelines/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def materials_guidelines(self, **form_data):
        values = {}; 
        return request.render("shc_published_paper.materials_guidelines", values)
    
    @http.route(['/materials_editorial/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def materials_editorial(self, **form_data):
        values = {}; 
        return request.render("shc_published_paper.materials_editorial", values)
    
    # Social Journal
    @http.route(['/social_home/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def social_home(self, **form_data):
        values = {}; 
        return request.render("shc_published_paper.social_home", values)
    
    @http.route(['/social_guidelines/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def social_guidelines(self, **form_data):
        values = {}; 
        return request.render("shc_published_paper.social_guidelines", values)
    
    @http.route(['/social_editorial/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def social_editorial(self, **form_data):
        values = {}; 
        return request.render("shc_published_paper.social_editorial", values)
    
     # Tamil Journal
    @http.route(['/tamil_home/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def tamil_home(self, **form_data):
        values = {}; 
        return request.render("shc_published_paper.tamil_home", values)
    
    @http.route(['/tamil_guidelines/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def tamil_guidelines(self, **form_data):
        values = {}; 
        return request.render("shc_published_paper.tamil_guidelines", values)
    
    @http.route(['/tamil_editorial/'], methods=['GET', 'POST'], type='http', auth="public", website=True)
    def tamil_editorial(self, **form_data):
        values = {}; 
        return request.render("shc_published_paper.tamil_editorial", values)

class Home(http.Controller):
            
    @http.route(['/web/binary/download_document/'], type='http', auth="public",  website=True, methods=['GET', 'POST'])
    def content_common(self, xmlid=None, model='ir.attachment', id=None, field='datas', filename=None, filename_field='datas_fname', unique=None, mimetype=None, download=None, data=None, token=None):
        ir_attachment_id = request.env['ir.attachment'].sudo().search([('id','=',id)])
        if ir_attachment_id:
            status, headers, content = binary_content(xmlid=xmlid, model=model, id=id, field=field, unique=unique, filename=ir_attachment_id.datas_fname, filename_field=filename_field, download=True, mimetype=mimetype)
            if status == 304:
                response = werkzeug.wrappers.Response(status=status, headers=headers)
            elif status == 301:
                return werkzeug.utils.redirect(content, code=301)
            elif status != 200:
                response = request.not_found()
            else:
                content_base64 = base64.b64decode(content)
                headers.append(('Content-Length', len(content_base64)))
                response = request.make_response(content_base64, headers)
            if token:
                response.set_cookie('fileToken', token)
            return response
        
    @http.route(['/web/binary/view_document/'], type='http', auth="public",  website=True, methods=['GET', 'POST'])
    def preview_journal(self, xmlid=None, model='ir.attachment', id=None, field='datas', filename=None, filename_field='datas_fname', unique=None, mimetype=None, download=None, data=None, token=None):
        status, headers, content = binary_content(xmlid=xmlid, model=model, id=id, field=field, unique=unique, filename=filename, filename_field=filename_field, download=download, mimetype=mimetype)
        if status == 304:
            response = werkzeug.wrappers.Response(status=status, headers=headers)
        elif status == 301:
            return werkzeug.utils.redirect(content, code=301)
        elif status != 200:
            response = request.not_found()
        else:
            content_base64 = base64.b64decode(content)
            headers.append(('Content-Length', len(content_base64)))
            response = request.make_response(content_base64, headers)
        if token:
            response.set_cookie('fileToken', token)
        return response
    
class download(http.Controller):  
    
    @http.route(['/web/binary/comman_download/'], type='http', auth="public",  website=True, methods=['GET', 'POST'])
    def content_common(self, name = '', document_name = '', xmlid=None, model='ir.attachment', id=None, field='datas', filename=None, filename_field='datas_fname', unique=None, mimetype=None, download=None, data=None, token=None):
        journal_id = request.env['res.company'].sudo().search([('name','like',name)])
        if journal_id:
            for doc_id in journal_id.document_multi_ids:
                if document_name in doc_id.name:
                    id = doc_id.id
                    break
        status, headers, content = binary_content(xmlid=xmlid, model=model, id=id, field=field, unique=unique, filename=document_name, filename_field=filename_field, download=True, mimetype=mimetype)
        if status == 304:
            response = werkzeug.wrappers.Response(status=status, headers=headers)
        elif status == 301:
            return werkzeug.utils.redirect(content, code=301)
        elif status != 200:
            response = request.not_found()
        else:
            content_base64 = base64.b64decode(content)
            headers.append(('Content-Length', len(content_base64)))
            response = request.make_response(content_base64, headers)
        if token:
            response.set_cookie('fileToken', token)
        return response
