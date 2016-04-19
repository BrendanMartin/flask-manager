from functools import partial
from math import ceil
from enum import Enum
import traceback

from flask import request, abort, url_for, flash, current_app
from werkzeug.datastructures import CombinedMultiDict

from flask_manager import views


# pylint: disable=abstract-method
class Component(views.View):
    role = None
    urls = None

    def __init__(self, controller, *args, **kwargs):
        """
        Args:
            controller (Controller): ``controller`` parent.
        """
        self.controller = controller
        super().__init__(*args, **kwargs)

    # {{{ Components
    def get_success_url(self, params=None, item=None):
        if params is None:
            return url_for(self.success_url)
        roles = self.controller.get_roles()
        name = roles[Roles.create.name][0]
        if '_continue_editing' in params and item is not None:
            return url_for('.{}'.format(name), pk=str(item.id))
        elif '_add_another' in params:
            return url_for('.{}'.format(name))
        return url_for(self.success_url)
    # }}}

    # {{{ View
    def dispatch_request(self, render='html', *args, **kwargs):
        if not self.is_allowed():
            abort(401)
        return super().dispatch_request(render, *args, **kwargs)

    def context(self, external_ctx=None):
        return super().context({
            'display_rules': self.controller.display_rules.get(self.role.name),
            'tree': self.controller.endpoints_tree(),
            'roles': self.controller.get_roles(),
            'success_url': self.success_url,
            **(external_ctx or {})
        })
    # }}}

    # {{{ Permissions
    def is_allowed(self):
        roles = self.controller.get_roles()
        allowed = roles.get(self.role.name, ())
        return self.view_name in allowed
    # }}}

    # {{{ Convenience
    def get_item(self, pk):
        item = self.controller.get_item(pk)
        if item is None:
            abort(404)
        return item

    def get_form_data(self):
        return CombinedMultiDict([request.form, request.files])

    def get_form(self, *args, **kwargs):
        return self.controller.form_class(*args, **kwargs)
    # }}}


class Roles(Enum):
    index = 1
    create = 2
    read = 3
    update = 4
    delete = 5


class Index(Component):
    role = Roles.index
    urls = (
        ('index.<any(html,json,tsv):render>', {}),
        ('index', {'render': 'html'})
    )
    template_name = ('crud/index.html', )

    def get(self):
        order_by = request.args.get('order_by')
        page = int(request.args.get('page', 1))

        filter_form = self.controller.get_filter_form()
        action_form = self.controller.get_action_form()
        url_generator = partial(
            url_for, request.url_rule.endpoint, **request.args)
        roles = self.controller.get_roles()
        has_roles = bool(
            roles.get('read') or
            roles.get('update') or
            roles.get('delete')
        )

        items, total = self.controller.get_items(
            page=page, order_by=order_by, filters=request.args)
        if self.controller.per_page == 0:
            pages = 0
        else:
            pages = ceil(total/self.controller.per_page)
        return {
            'forms': {
                'filter': {'show': bool(self.controller.filters),
                           'form': filter_form(request.args)},
                'action': {'show': bool(self.controller.actions),
                           'form': action_form()},
            },
            'has_roles': has_roles,
            'pagination': {
                'order_by': order_by,
                'page': page,
                'total': total,
                'pages': pages,
                'url_generator': url_generator,
            },
            'items': items,
        }

    def post(self):
        self.controller.execute_action(self.get_form_data())
        return self.get_success_url(), {}


class Create(Component):
    role = Roles.create
    urls = (('create', {}),)
    template_name = ('crud/form.html', 'crud/create.html')

    def get(self):
        form_data = self.get_form_data()
        form = self.get_form(form_data)
        return {'form': form}

    def post(self):
        form_data = self.get_form_data()
        form = self.get_form(form_data)
        success_url = None
        if form.validate():
            try:
                item = self.controller.create_item(form)
            except Exception as e:  # pylint: disable=broad-except
                current_app.logger.error(traceback.format_exc())
                flash(str(e))
            else:
                success_url = self.get_success_url(form_data, item)
        return success_url, {'form': form}


class Read(Component):
    role = Roles.read
    urls = (('read/<pk>', {}),)
    template_name = ('crud/read.html', )

    def get(self, pk):
        item = self.get_item(pk)
        return {'pk': pk, 'item': item}


class Update(Component):
    role = Roles.update
    urls = (('update/<pk>', {}),)
    template_name = ('crud/form.html', 'crud/update.html')

    def get(self, pk):
        item = self.get_item(pk)
        form = self.get_form(self.get_form_data(), obj=item)
        return {'pk': pk, 'item': item, 'form': form}

    def post(self, pk):
        form_data = self.get_form_data()
        item = self.get_item(pk)
        form = self.get_form(form_data, obj=item)
        success_url = None
        if form.validate():
            try:
                self.controller.update_item(item, form)
            except Exception as e:  # pylint: disable=broad-except
                current_app.logger.error(traceback.format_exc())
                flash(str(e))
            else:
                success_url = self.get_success_url(self.get_form_data(), item)
        return success_url, {'pk': pk, 'item': item, 'form': form}


class Delete(Component):
    role = Roles.delete
    urls = (('delete/<pk>', {}),)
    template_name = ('crud/delete.html', 'crud/read.html')

    def get(self, pk):
        item = self.get_item(pk)
        return {'pk': pk, 'item': item}

    def post(self, pk):
        item = self.get_item(pk)
        success_url = None
        try:
            self.controller.delete_item(item)
        except Exception as e:  # pylint: disable=broad-except
            current_app.logger.error(traceback.format_exc())
            flash(str(e))
        else:
            success_url = url_for(self.success_url)
        return success_url, {'pk': pk, 'item': item}
