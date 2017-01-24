from __future__ import absolute_import

from django import forms
from django.db.models import Q
from django.contrib.auth.models import Group

from admin.common_auth.models import AdminProfile


class LoginForm(forms.Form):
    email = forms.CharField(label=u'Email', required=True)
    password = forms.CharField(
        label=u'Password',
        widget=forms.PasswordInput(render_value=False),
        required=True
    )


class UserRegistrationForm(forms.Form):
    """ A form that finds an existing OSF User, and grants permissions to that
    user so that they can use the admin app"""

    osf_id = forms.CharField(required=True, max_length=5, min_length=5)

    group_perms = forms.ModelMultipleChoiceField(
        queryset=Group.objects.filter(Q(name='prereg_group') | Q(name='osf_admin')),
        required=True
    )


class DeskUserForm(forms.ModelForm):
    class Meta:
        model = AdminProfile
        fields = ['desk_token', 'desk_token_secret']
