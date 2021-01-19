#! usr/bin/python
#coding=utf-8

from django.http import HttpResponse
from django.shortcuts import render_to_response,render
from django.shortcuts import HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.core.servers.basehttp import FileWrapper
import os
import time
import datetime
import sys
sys.path.append("..")
from common.api.db import MySqlconn
import json
import yaml
from common.api.f5api import F5Api
from common.api.login_ldap import login_check
from common.api.config import GetConfig
from logwrite import AutoupLog
from upfun import Upfun
from haproxy.etcdapi import EtcdApi
from celery_check import after_check
import redis
from hotfix_mail import hotfixmail_over,hotfixmail_fail
from haproxy import nginx
from common.api import kong
from dllup_v2 import TimeNow
import const
import datetime
log_write = AutoupLog()
etcdctrl = EtcdApi()
configget = GetConfig()
redis_connect_info = configget.get_config('/home/saltoneops-1.0.0/common/conf/redis.conf','redis_hotfix',section='')
redis_ip = redis_connect_info['redis_host']
redis_port = redis_connect_info['redis_port']
redis_db = redis_connect_info['redis_db']

r = redis.Redis(host=redis_ip,port=redis_port,db=redis_db)

redis_connect_info = configget.get_config('/home/saltoneops-1.0.0/common/conf/redis.conf','redis_hotfix_mutex',section='')
redis_ip = redis_connect_info['redis_host']
redis_port = redis_connect_info['redis_port']
redis_db = redis_connect_info['redis_db']
mutex = redis.Redis(host=redis_ip,port=redis_port,db=redis_db)


funtiondic = const.funtiondic
status = const.status
publish_status = const.publish_status


@login_check('/dllup/hotpublish/')
def hotfix_publish(request):

    a = MySqlconn()
    if 'sa' in request.session.get('info')['userrole']:
        hotfixlist = a.get_results('hotfix_info', ['publishteam','createuser','hotfixid', 'hotfixcontain', 'createtime', 'hotfixstatus','publishuser'],
                               { 'enabled': 1}, 'createtime',False,(0,100),None)
    else:
        userdata  = request.session.get('info')['name']
        print userdata,'111111111111111'
        print request.session.get('info')
        hotfixlist = a.get_results('hotfix_info',
                                   ['publishteam','createuser', 'hotfixid', 'hotfixcontain', 'createtime', 'hotfixstatus',
                                    'publishuser'],
                                   {'enabled': 1,'createuser':userdata}, 'createtime',False,(0,50),None)


    if not TimeNow():
        status['1'] = '<p class="text-aqua">非工作时间hotfix<br/>请联系产品负责人进行审核处理</p>'
    else:
        status['1'] = '<p class="text-aqua">定制完成，待发布</p>'

    result_data = []
    if hotfixlist:
        for i in hotfixlist:
            resultover = a.get_one_result('publish_info', ['count(1)'],
                                          {'hotfix_id': int(i['hotfixid']), 'publish_status': '1'}, False, False, False)
            resultcount = a.get_one_result('publish_info', ['count(1)'], {'hotfix_id': int(i['hotfixid'])}, False,
                                           False, False)
            resultroletmp = a.get_results('publish_info', ['publish_role'], {'hotfix_id': int(i['hotfixid'])}, False,
                                           False, False)
            if 'sql' in [x['publish_role'] for x in resultroletmp]:
                i['hotfixcontain'] = '<span class="badge bg-orange">SQL</span>' + i['hotfixcontain']

            if int(resultover['count(1)']) == 0 or int(resultcount['count(1)']) == 0:
                persent = '0%'
            else:
                persent = "%.2f%%" % ((float(resultover['count(1)']) / float(resultcount['count(1)']) * 100))

            if int(i['hotfixstatus']) in [0,3,4,5,6]:
                disable = r'disabled = "disabled"'
            else:
                disable = ''


            i['createtime'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(i['createtime']))
            i['resultcount'] = int(resultcount['count(1)'])
            i['status'] = status[str(int(i['hotfixstatus']))]
            i['persent'] = persent
            i['disable'] = disable

            result_data.append(i)

    return render(request, 'dllup/hotfix_publish.html', {'result': result_data})



def hotfix_publish_get(request):
    a = MySqlconn()
    hotfixlist = a.get_results('hotfix_info',
                               ['createuser', 'hotfixid', 'hotfixcontain', 'createtime', 'hotfixstatus', 'publishuser'],
                               {'enabled': 1}, 'createtime', False, (0, 100), None)
    result_data = []
    if hotfixlist:
        for i in hotfixlist:
            resultover = a.get_one_result('publish_info', ['count(1)'],
                                          {'hotfix_id': int(i['hotfixid']), 'publish_status': '1'}, False, False, False)
            resultcount = a.get_one_result('publish_info', ['count(1)'], {'hotfix_id': int(i['hotfixid'])}, False,
                                           False, False)
            if int(resultover['count(1)']) == 0 or int(resultcount['count(1)']) == 0:
                persent = '0%'
            else:
                persent = "%.2f%%" % ((float(resultover['count(1)']) / float(resultcount['count(1)']) * 100))

            if int(i['hotfixstatus']) in [0, 3, 4, 5]:
                disable = r'disabled = "disabled"'
            else:
                disable = ''

            i['createtime'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(i['createtime']))
            i['resultcount'] = int(resultcount['count(1)'])
            i['status'] = status[str(int(i['hotfixstatus']))]
            i['persent'] = persent
            i['disable'] = disable

            result_data.append(i)
    return HttpResponse(json.dumps(result_data))



def hotfixover(request,hotfixid):
    username = request.session.get('info', None)['cn']
    a = MySqlconn()
    a.execute_update_sql('hotfix_info', {'hotfixstatus': 3,'finishtime':str(int(time.mktime(datetime.datetime.now().timetuple())))}, {'hotfixid': hotfixid}, None)
    hotfixinfo = a.get_one_result('hotfix_info',['createuser','publishteam'],{'hotfixid':hotfixid},False,False,False)
    r.delete(hotfixinfo['createuser'])
    proj = a.get_results('publish_info',['publish_website'],{'hotfix_id':hotfixid})
    for p in proj:
        mutex.delete(p['publish_website'])
    if hotfixinfo['publishteam'] == 'Ocean':
        hotfixmail_over(hotfixid, username, hotfixinfo['createuser'],'v_bi@beisen.com')
    else:
        hotfixmail_over(hotfixid,username,hotfixinfo['createuser'])
    #hotfixmail_over(hotfixid,username,hotfixinfo['createuser'])
    return HttpResponseRedirect('/dllup/hotpublish/')

def hotfixstart(hotfixid,username):
    a = MySqlconn()
    data = {}
    data['hotfixstatus'] = 2
    data['publishuser'] =username
    a.execute_update_sql('hotfix_info', data, {'hotfixid': hotfixid}, None)

def hotrollback(hotfixid,username):
    a = MySqlconn()
    data = {}
    data['hotfixstatus'] = 5
    data['publishuser'] =username
    a.execute_update_sql('hotfix_info', data, {'hotfixid': hotfixid}, None)

#hotfix 驳回
def hotfixreject(request,hotfixid):
    username = request.session.get('info', None)['cn']

    a = MySqlconn()
    hotfixinfo = a.get_one_result('hotfix_info', ['createuser'], {'hotfixid': hotfixid}, False, False, False)
    if not r.get(hotfixinfo['createuser']):
        a.execute_update_sql('hotfix_info', {'hotfixstatus': 0}, {'hotfixid': hotfixid}, None)
        r.delete(hotfixinfo['createuser'], hotfixid)
        return HttpResponseRedirect('/dllup/hotpublish/')
    else:
        return HttpResponseRedirect('/dllup/hotpublish/')


def hotfixfail(request,hotfixid):
    a = MySqlconn()
    username = request.session.get('info', None)['cn']

    if request.method == 'GET':
        status = {'0': '未发布', '1': '发布完成'}
        result_a = a.get_results('publish_info',
                                 ['publish_time', 'publish_user', 'publish_product', 'publish_website', 'publish_info',
                                  'publish_status', 'publish_id', 'publish_role'], {'hotfix_id': hotfixid},
                                 'publish_time',
                                 False, (0, 100))
        failtype = a.get_results('hotfix_failtype_info',['failtype'],None,None,True,None)
        result_html = []
        for i in result_a:
            result_str = '<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td> <button type="button" class="btn btn-primary" target="main" onclick="javascript:window.location.href=\'/dllup/publish_info/%s\';">查看发布详情</button></td></tr>' % (
                time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(i['publish_time'])), i['publish_user'],
                i['publish_role'],
                i['publish_product'], i['publish_website'], status[str(i['publish_status'])], i['publish_id'])
            result_html.append(result_str)
        return  render(request,'dllup/hotfix_failinfo.html',{'result':result_html,'hotfixid':hotfixid,'failtype':failtype})
    elif request.method =='POST':
        failinfo = request.POST.get('hotfixfail','')
        data = {}
        data['failtype'] = request.POST.get('failtype','')
        data['hotfixstatus'] = 4
        data['finishtime'] = str(int(time.mktime(datetime.datetime.now().timetuple())))
        if  failinfo != '':
            data['failinfo'] = '<br\>'.join(failinfo.split('\n'))
        else:
            data['failinfo'] = failinfo
        a.execute_update_sql('hotfix_info',data, {'hotfixid': hotfixid}, None)
        hotfixinfo = a.get_one_result('hotfix_info', ['createuser'], {'hotfixid': hotfixid}, False, False, False)
        r.delete(hotfixinfo['createuser'])
        hotfixmail_fail(hotfixid,username,hotfixinfo['createuser'])
        return HttpResponseRedirect('/dllup/hotpublish/')


@login_check('/dllup/hotpublish/')
def dll_publish(request,hotfixid):
    username = request.session.get('info', None)['cn']
    status = {'0': '未发布', '1': '发布完成'}
    a = MySqlconn()
    result_b = a.get_one_result('hotfix_info', ['hotfix_depict'], {'hotfixid': hotfixid}, None,
                                True, None)
    result_a = a.get_results('publish_info',['publish_time','publish_user','publish_product','publish_website','publish_info','publish_status','publish_id','publish_role'],{'hotfix_id':hotfixid},'publish_time',False,(0,100))
    result_html=[]
    hotfixstart(hotfixid,username)
    for i in result_a:
        result_str = '<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td> \
                     <td> <button type="button" class="btn btn-warning btn-sm " target="main" onclick="javascript:window.location.href=\'/dllup/dll_uppage/%s/%s\';">发布</button>\
                   <button type="button" class="btn btn-info btn-sm " target="main" onclick="javascript:window.location.href=\'/dllup/publishover/%s\';">完成</button> \
                    <button type="button" class="btn btn-error btn-sm " target="main" onclick="javascript:window.location.href=\'/dllup/filedown/%s\';">下载</button> \
        <button type="button" class="btn btn-success btn-sm " target="main" onclick="javascript:window.location.href=\'/dllup/publish_info/%s\';">详情</button> </td> \
                     </tr>'%(time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(i['publish_time'])),funtiondic[i['publish_role']],i['publish_user'],i['publish_product'],i['publish_website'],status[str(i['publish_status'])],i['publish_role'],i['publish_id'],i['publish_id'],i['publish_id'],i['publish_id'])
        result_html.append(result_str)

    if result_b['hotfix_depict']:
        hotfix_all_info = result_b['hotfix_depict'].replace('\r\n','<br/>')
    else:
        hotfix_all_info = ''

    return render(request,'dllup/dll_publish.html',{'result':result_html,'hotfix_dep':hotfix_all_info,'hotfix_id':hotfixid})

@login_check('/dllup/hotpublish/')
def dllrollback(request,hotfixid):
    username = request.session.get('info', None)['cn']
    status = {'0': '未发布', '1': '发布完成'}
    a = MySqlconn()
    result_a = a.get_results('publish_info',['publish_time','publish_user','publish_product','publish_website','publish_info','publish_status','publish_id','publish_role'],{'hotfix_id':hotfixid},'publish_time',False,(0,100))
    result_html=[]
    hotrollback(hotfixid,username)
    for i in result_a:
        result_str = '<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td> \
                     <td> <button type="button" class="btn btn-warning btn-sm " target="main" onclick="javascript:window.location.href=\'/dllup/dll_uppage/%s/%s\';">发布</button>\
                   <button type="button" class="btn btn-info btn-sm " target="main" onclick="javascript:window.location.href=\'/dllup/publishover/%s\';">完成</button> \
                    <button type="button" class="btn btn-error btn-sm " target="main" onclick="javascript:window.location.href=\'/dllup/filedown/%s\';">下载</button> \
        <button type="button" class="btn btn-success btn-sm " target="main" onclick="javascript:window.location.href=\'/dllup/publish_info/%s\';">详情</button> </td> \
                     </tr>'%(time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(i['publish_time'])),funtiondic[i['publish_role']],i['publish_user'],i['publish_product'],i['publish_website'],status[str(i['publish_status'])],i['publish_role'],i['publish_id'],i['publish_id'],i['publish_id'],i['publish_id'])
        result_html.append(result_str)
    return render(request,'dllup/dll_publish.html',{'result':result_html})

def publishover(request,publish_id):
    a = MySqlconn()
    proj = a.get_one_result('publish_info', ['publish_website'],{ 'publish_id': publish_id},)
    mutex.delete(proj['publish_website'])
    a.execute_update_sql('publish_info',{'publish_status':1,'finishtime':str(int(time.mktime(datetime.datetime.now().timetuple())))},{'publish_id':publish_id},None)
    hotfix_id = a.get_one_result('publish_info',['hotfix_id'],{'publish_id':publish_id},False,False,False)['hotfix_id']
    return HttpResponseRedirect('/dllup/dllpublish/%s/'%hotfix_id)

def filedown(request,publish_id):
    if request.method == 'GET':
        a = MySqlconn()
        result = a.get_one_result('publish_info',['publish_tmppath'],{'publish_id':publish_id},False,False,False)

        os.system('cd /tmp/softzip_tmp/;zip -r %s.zip  %s' % (publish_id, result['publish_tmppath']))
        file1 = '/tmp/softzip_tmp/%s.zip' % publish_id
        wrapper = FileWrapper(file(file1))
        response = HttpResponse(wrapper, content_type='text/plain')
        response['Content-Length'] = os.path.getsize(file1)
        response['Content-Encoding'] = 'utf-8'
        response['Content-Disposition'] = 'attachment;filename=%s' % file1.split('/')[-1]
        return response

def dll_f5status(request, app):
    app = app.lower()
    if get_ngpool_name(app):
        result = nginx.get_conn_num_for_oneops(request,app)
        print app,result
        return result
    else:
        a = MySqlconn()
    #    sql = 'select a.ipaddress from dllout_server a,dllout_role b,dllout_product c where c.domainname = \"%s\" and b.ippid = c.id and a.id = b.serverid order by domainname'%app
        sql = 'SELECT t4.ip_add From opsapp_apps t1 \
              INNER JOIN opsapp_appname t2 on t2.id=t1.name_id \
              INNER JOIN opsapp_apps_ip_add t3 on t1.id=t3.apps_id \
              INNER JOIN opsapp_serverip t4 on t4.id=t3.serverip_id \
              WHERE t2.name=\'%s\''%app
        result = []
        f5 = F5Api()
        for i in a.query(sql):
            status_a =  f5.Membercheck(app,i[0])[1]
            if status_a == "enabled" :
                result.append({'b' + i[0].replace('.',''):'<span class="badge bg-green">在线</span>'})
            else:
                result.append({'b' + i[0].replace('.', ''): '<span class="badge bg-red">离线</span>'})
            time.sleep(1)
            result.append({'a' + i[0].replace('.',''):f5.Membercheck(app,i[0])[0]})
        rjson = json.dumps(result)
        response = HttpResponse()
        response['Content-Type'] = "text/javascript"
        response.write(rjson)
        return response


@csrf_exempt
@login_check('/dllup/hotpublish/')
def dll_uppage(request,dll_uppage):
    if request.method == 'GET':
        a = MySqlconn()
        result_a = a.get_one_result('publish_info',['hotfix_id','publish_tmppath','publish_contain','publish_time','publish_user','publish_product','publish_website','publish_info','publish_id'],{'publish_id':dll_uppage},'publish_time',False,(0,100))
        result_a['publish_time']=time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(result_a['publish_time']))
#        sql = 'select a.ipaddress,b.filepath,c.domainname from dllout_server a,dllout_role b,dllout_product c where c.domainname = \"'  + result_a['publish_website']  + '\" and b.ippid = c.id and a.id = b.serverid order by domainname'
        sql = 'SELECT t4.ip_add,t1.app_path,t2.name From opsapp_apps t1 \
              INNER JOIN opsapp_appname t2 on t2.id=t1.name_id \
              INNER JOIN opsapp_apps_ip_add t3 on t1.id=t3.apps_id \
              INNER JOIN opsapp_serverip t4 on t4.id=t3.serverip_id \
              WHERE t2.name=\'%s\''%result_a['publish_website']
        result_b = []
        result_b.append('<input type="hidden" name="jobid" value="%s">'%result_a['publish_id'])
        result_jshtml = []
        for i in a.query(sql):
            result_str = '<tr><td><input type="checkbox" name="update" value="%s"></td><td>%s</td><td>%s</td><td><div id="a%s"></div></td><td><div id="b%s"></td><td> <button  class="btn btn-primary" type="submit" name="f5sta" value="disabled,%s">Kong下线</button>&nbsp<button  class="btn btn-primary" type="submit" name="f5sta" value="enabled,%s">Kong上线</button></td></tr>'%(i[0],i[0],i[1],i[0].replace('.',''),i[0].replace('.',''),i[0],i[0])
            tag = i[0].replace('.','')
            result_jshtml.append('$("#a%s").html( this.a%s );'%(tag,tag))
            result_jshtml.append('$("#b%s").html( this.b%s );'%(tag,tag))
            result_b.append(result_str)
        result_a['updone'] = result_b
        result_a['upjs']= result_jshtml
        result_a['appname']='\'' +result_a['publish_website'] + '\''
        return render_to_response('dllup/uppage.html',result_a)
    elif request.method == 'POST':
        f5updown = F5Api()
        jobid = request.POST.get('jobid')
        a = MySqlconn()
        result_a = a.get_one_result('publish_info',['publish_tmppath','publish_contain','publish_time','publish_user','publish_product','publish_website','publish_info','publish_id','publish_role'],{'publish_id':jobid},'publish_time',False,(0,100))
        if request.POST.has_key('upfun'):
            ip = request.POST.getlist('update')
            upfun = request.POST.get('upfun')
            log_write = AutoupLog()
            log_write.autolog_write('critical','开始任务号为%s的发布任务，配置文件为/srv/salt/%s/sls%s.sls'%(jobid,jobid,jobid),jobid)
            b = Upfun()
            if len(ip):
                if upfun == 'upall':
                    log_write.autolog_write('critical', '采用直接滚动升级方式，开始更新',jobid)
                    b.upall(jobid,result_a['publish_user'],ip)
                elif upfun == 'f5updown':
                    log_write.autolog_write('critical', '采用切F5滚动升级方式，开始更新',jobid)
                    b.f5updown(jobid,result_a['publish_user'],ip,result_a['publish_website'])
                elif upfun == 'updirect':
                    log_write.autolog_write('critical', '采用直接升级方式，开始更新', jobid)
                    b.updirect(jobid, result_a['publish_user'], ip)
                elif upfun == 'rollback':
                    log_write.autolog_write('critical', '执行回滚操作，开始回滚', jobid)
                    b.rollback(jobid,result_a['publish_user'],ip)
                elif upfun == 'f5down':
                    # if get_ngpool_name(result_a['publish_website'].lower()):
                    log_write.autolog_write('critical', '执行Kong下线操作，下线IP为%s' % ','.join(ip), jobid)
                    kong.kong_down(jobid, ip, result_a['publish_website'].lower())
                        # b.ng_down(jobid, result_a['publish_user'], ip, result_a['publish_website'].lower())
                        # b.f5down(jobid, result_a['publish_user'], ip, result_a['publish_website'].lower())
                    # else:
                    #     kong.kong_up(jobid, ip, result_a['publish_website'].lower())
                        # log_write.autolog_write('critical', '执行F5下线操作，下线IP为%s'%','.join(ip), jobid)
                        # b.f5down(jobid,result_a['publish_user'],ip,result_a['publish_website'].lower())
                elif upfun == 'f5up':
                    #if get_ngpool_name(result_a['publish_website']):
                    log_write.autolog_write('critical', '执行Kong上线操作，上线IP为%s' % ','.join(ip), jobid)
                    kong.kong_up(jobid, ip, result_a['publish_website'].lower())
                    #    b.ng_up(jobid,result_a['publish_user'],ip,result_a['publish_website'].lower())
                    #    b.f5up(jobid, result_a['publish_user'], ip, result_a['publish_website'].lower())
                    # else:
                    #     log_write.autolog_write('critical', '执行F5上线操作，上线IP为%s' % ','.join(ip), jobid)
                    #     b.f5up(jobid, result_a['publish_user'], ip, result_a['publish_website'].lower())
            else:
                log_write.autolog_write('critical', '选择操作的IP', jobid)
        elif request.POST.has_key('alllog'):
            return render_to_response('dllup/alllogtext.html',{'jobid':jobid})
        elif request.POST.has_key('f5sta'):
            # b = Upfun()
            f5sta = request.POST.get('f5sta')
            log_write = AutoupLog()
            # if get_ngpool_name(result_a['publish_website']):
            log_write.autolog_write('critical', '操作Kong，执行动作为%s' % f5sta, jobid)
            kong.kong_up_down(result_a['publish_website'].lower(),f5sta.split(',')[1],f5sta.split(',')[0])
                # b.ng_up_down(result_a['publish_website'].lower(),f5sta.split(',')[1],f5sta.split(',')[0])
                # f5updown.Memberupdown(result_a['publish_website'].lower(), f5sta.split(',')[1], f5sta.split(',')[0])
            # else:
            #     log_write.autolog_write('critical','操作F5，执行动作为%s'%f5sta,jobid)
            #     f5updown.Memberupdown(result_a['publish_website'].lower(),f5sta.split(',')[1],f5sta.split(',')[0])
        response = HttpResponseRedirect('/dllup/dll_uppage/%s/%s'%(result_a['publish_role'],jobid))
        return  response


def log_status(request, jobid):
    result = os.popen('cat /srv/salt/%s/%s.log |grep  -i -E \'error|critical|saltup_backup\'|grep -v \'xcopy\'|grep -v \'{{grains.id}}\'| tail -n 200'%(jobid,jobid)).readlines()
    result_a = [{'a' + jobid:''.join(result).replace('\n','<br/>')}]
    rjson = json.dumps(result_a)
    response = HttpResponse()
    response['Content-Type'] = "text/javascript"
    response.write(rjson)
    return response


def get_ngpool_name(appname):
    a = MySqlconn()
    appname = appname.lower()
    result = a.get_one_result('opsapp_appname', ['nginxname'], {'name': appname}, )
    if result['nginxname'] == 'ng_' + appname:
        return True
    else:
        return False

def alllog_status(request, jobid):
    result = os.popen('cat /srv/salt/%s/%s.log'%(jobid,jobid)).readlines()
    result_a = [{'a' + jobid:''.join(result).replace('\n','<br/>')}]
    rjson = json.dumps(result_a)
    response = HttpResponse()
    response['Content-Type'] = "text/javascript"
    response.write(rjson)
    return response


def logview(request,jobid):
    return render_to_response('dllup/logtext.html',{'jobid':jobid})


def alllogview(request,jobid):
    return render_to_response('dllup/alllogtext.html',{'jobid':jobid})

def bbaatest():
    log_write.autolog_write('critical', '回滚完成', '1464054055')

if __name__=='__main__':
#    a = Upfun()
#    m = a.f5updown('1464054055','liwei',['10.22.1.156','10.22.1.166'],'epm.tita.com')
    get_f5pool_name('lihe.test.com')
