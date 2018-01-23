 # -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
from django.shortcuts import render, redirect, HttpResponse
from django.core.urlresolvers import reverse
from django.conf import settings
from django.contrib.auth import logout, login, authenticate
from django.contrib.auth.hashers import make_password
from django.core.paginator import Paginator, InvalidPage, EmptyPage, PageNotAnInteger
from django.db import connection
from django.db.models import Count
from models import *
from forms import *
import json

# Create your views here.
logger = logging.getLogger('blog.views')

'''#定义一个获取全局变量的方法中间件，通过在settings中配置该中间件，当每一次请求，都会执行该方法，将一些参数返回'''
def global_setting(request):
    #分类信息获取
    category_list = Category.objects.all()
    #文章归档列表
    archive_list = Article.objects.distinct_date()
    #文章归档
    #先获取到文章中有年份-月份
    #Article.objects.raw("select * from blog_article")可以直接执行sql语句，该种方法查询必须要有主键
    #另一种执行sql方法：导入django import connection
    """
        from django.db import connection

        def my_custom_sql(self):
            with connection.cursor() as cursor:
                cursor.execute("UPDATE bar SET foo = 1 WHERE baz = %s", [self.baz])
                cursor.execute("SELECT foo FROM bar WHERE baz = %s", [self.baz])
                row = cursor.fetchone()
        
            return row
    """
    #标签栏
    tag_list = Tag.objects.all()
    #友情链接
    link_list = Links.objects.all()
    #浏览排行
    click_article_list = Article.objects.order_by('-click_count')[:5]
    #评论排行
    comment_count_list = Comment.objects.values('article').annotate(comment_count=Count('article')).order_by('-comment_count')#文章聚合查询
    comment_article_list = [Article.objects.get(pk=comment['article']) for comment in comment_count_list]
    #站长推荐
    recommend_article_list = Article.objects.filter(is_recommend=True)[:5]
    #广告
    SITE_DESC = settings.SITE_DESC
    SITE_NAME = settings.SITE_NAME
    return locals()


'''首页处理'''
#设置缓存，每1分钟更新一次
# @cache_page(60*1, key_prefix='blog_project')
def index(request):
    try:
        #广告数据
        #最新文章数据
        article_list = getpage(request,Article.objects.all())
    except Exception as e:
        logger.error(e)
    return render(request,'index.html', locals())#locals()将作用域所有的变量封装并返回

'''
文章归档处理
'''
def archive(request):
    try:
        #先获取客户端提交信息
        year = request.GET['year']
        month = request.GET['month']
        article_list = Article.objects.filter(date_publish__icontains=year+'-'+month)#date_publish__icontains模糊查询，其中i表示忽略大小写
        article_list = getpage(request,article_list)
    except Exception as e:
        logger.error(e)
    return render(request,'archive.html',locals())

 # 分页代码
def getpage(request,article_list):
    paginator = Paginator(article_list,settings.PAGE_SIZE)
    try:
        page = int(request.GET.get('page',1))
        article_list = paginator.page(page)
    except (EmptyPage,InvalidPage,PageNotAnInteger) as e:
        logger.error(e)
        article_list = paginator.page(1)
    return article_list

'''文章详情'''
def article(request):
    try:
        id = request.GET.get('id',None)
        try:
            article = Article.objects.get(pk=id)
        except Article.DoesNotExist:
            return render(request, 'failure.html', {'reason': '没有找到对应的文章'})
        # 评论表单
        comment_form = CommentForm({'author': request.user.username,
                                    'email': request.user.email,
                                    'url': request.user.url,
                                    'article': id} if request.user.is_authenticated() else{'article': id})
        # 获取评论信息
        comments = Comment.objects.filter(article=article).order_by('id')
        comment_list = []
        for comment in comments:
            for item in comment_list:
                if not hasattr(item, 'children_comment'):
                    setattr(item, 'children_comment', [])
                if comment.pid == item:
                    item.children_comment.append(comment)
                    break
            if comment.pid is None:
                comment_list.append(comment)
    except Exception as e:
        logger.error(e)
    return render(request, 'article.html', locals())

def comment_post(request):
    try:
        comment_form = CommentForm(request.POST)
        if comment_form.is_valid():
            #获取表单信息
            comment = Comment.objects.create(username=comment_form.cleaned_data["author"],
                                             email=comment_form.cleaned_data["email"],
                                             url=comment_form.cleaned_data["url"],
                                             content=comment_form.cleaned_data["comment"],
                                             article_id=comment_form.cleaned_data["article"],
                                             user=request.user if request.user.is_authenticated() else None)
            comment.save()
        else:
            return render(request, 'failure.html', {'reason': comment_form.errors})
    except Exception as e:
        logger.error(e)
    return redirect(request.META['HTTP_REFERER'])

# 注销
def do_logout(request):
    try:
        logout(request)
    except Exception as e:
        print e
        logger.error(e)
    return redirect(request.META['HTTP_REFERER'])

 # 注册
def do_reg(request):
     try:
         if request.method == 'POST':
             reg_form = RegForm(request.POST)
             if reg_form.is_valid():
                 # 注册
                 user = User.objects.create(username=reg_form.cleaned_data["username"],
                                            email=reg_form.cleaned_data["email"],
                                            url=reg_form.cleaned_data["url"],
                                            password=make_password(reg_form.cleaned_data["password"]),)
                 user.save()

                 # 登录
                 user.backend = 'django.contrib.auth.backends.ModelBackend' # 指定默认的登录验证方式
                 login(request, user)
                 return redirect(request.POST.get('source_url'))
             else:
                 return render(request, 'failure.html', {'reason': reg_form.errors})
         else:
             reg_form = RegForm()
     except Exception as e:
         logger.error(e)
     return render(request, 'reg.html', locals())

 # 登录
def do_login(request):
     try:
         if request.method == 'POST':
             login_form = LoginForm(request.POST)
             if login_form.is_valid():
                 # 登录
                 username = login_form.cleaned_data["username"]
                 password = login_form.cleaned_data["password"]
                 user = authenticate(username=username, password=password)
                 if user is not None:
                     user.backend = 'django.contrib.auth.backends.ModelBackend' # 指定默认的登录验证方式
                     login(request, user)
                 else:
                     return render(request, 'failure.html', {'reason': '登录验证失败'})
                 return redirect(request.POST.get('source_url'))
             else:
                 return render(request, 'failure.html', {'reason': login_form.errors})
         else:
             login_form = LoginForm()
     except Exception as e:
         logger.error(e)
     return render(request, 'login.html', locals())

def category(request):
     try:
         # 先获取客户端提交的信息
         cid = request.GET.get('cid', None)
         try:
             category = Category.objects.get(pk=cid)
         except Category.DoesNotExist:
             return render(request, 'failure.html', {'reason': '分类不存在'})
         article_list = Article.objects.filter(category=category)
         article_list = getpage(request, article_list)
     except Exception as e:
         logger.error(e)
     return render(request, 'category.html', locals())