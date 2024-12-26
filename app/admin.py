from flask import redirect, request, url_for, render_template, flash
from flask_admin.helpers import get_url
from markupsafe import Markup
from app import app, db, dao, utils
from flask_login import login_user, logout_user
from flask_admin import Admin, BaseView, expose, AdminIndexView
from app.models import Book, Review, Order, Voucher, Permission, Category, User, Configuration, RoleHasPermission
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user, login_user
from app.models import Role
from wtforms.fields import StringField
import calendar
from flask_admin.form import FileUploadField
from wtforms import FileField
import cloudinary
from wtforms_sqlalchemy.fields import QuerySelectField
from flask_admin.form import rules
from wtforms import Form
from datetime import datetime

def _image_formatter(view, context, model, name):
    # Kiểm tra nếu thuộc tính `name` có giá trị
    if getattr(model, name):
        return Markup(f'<img src="{getattr(model, name)}" style="width: 50px; height: auto;">')
    # Nếu không có `name`, kiểm tra `avata_file`
    if getattr(model, 'avatar_file'):
        return Markup(f'<img src="{model.avatar_file}" style="width: 50px; height: auto;">')
    # Trả về nếu không có hình ảnh
    return Markup('<span>No Image</span>')


def _truncate_formatter(view, context, model, name):
    text = getattr(model, name)  # Lấy giá trị từ model
    if text:
        # Lấy 10 từ đầu tiên và thêm "..." nếu có nhiều hơn
        truncated_text = ' '.join(text.split()[:10]) + ("..." if len(text.split()) > 10 else "")
        return truncated_text
    return ""


class AuthenticatedView(ModelView):
    required_permission = None  # Quyền cần thiết để truy cập view

    def is_accessible(self):
        if not current_user.is_authenticated:
            return False

        # Lấy danh sách tên quyền từ Role.permissions
        user_permissions = [
            permission.name  # Truy cập trực tiếp thuộc tính name
            for permission in current_user.role.permissions
        ]

        # Lấy quyền cần thiết cho view
        required_permission = getattr(self, 'required_permission', None)

        # Kiểm tra quyền
        return required_permission in user_permissions if required_permission else False

    can_view_details = True
    can_export = True
    edit_modal = True
    details_modal = True
    page_size = 10
    can_export = True

    form_excluded_columns = ['created_at', 'updated_at']


class AuthenticatedBaseView(BaseView):
    required_permission = None  # Quyền cần thiết để truy cập view

    def is_accessible(self):
        if not current_user.is_authenticated:
            return False
        # Lấy danh sách tên quyền từ Role.permissions
        user_permissions = [
            permission.name  # Truy cập trực tiếp thuộc tính name
            for permission in current_user.role.permissions
        ]
        # Lấy quyền cần thiết cho view
        required_permission = getattr(self, 'required_permission', None)

        # Kiểm tra quyền
        return required_permission in user_permissions if required_permission else False


class LogoutView(AuthenticatedBaseView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role.name in ["Admin", "Sales", "Storekeeper"]

    @expose("/")
    def index(self):
        logout_user()
        return redirect("/admin")


class StatsView(AuthenticatedBaseView):
    required_permission = "view_reports"  # Quyền cần thiết

    @expose("/")
    def index(self):
        month = request.args.get('month', default=None, type=int)
        print(month)
        year = request.args.get('year', default=datetime.now().year, type=int)
        print(year)
        if month:
            stats = dao.revenue_stats_by_time(time='month', year=year,month=month)
            stats2 =dao.stat_book_by_month_and_year(year=year,month=month)
        else:
            stats = dao.revenue_stats_by_time(time='year', year=year, month=month)
            stats2 = dao.stat_book_by_month_and_year(year=year,month=month)

        stats = [(idx + 1, *stat) for idx, stat in enumerate(stats)]
        stats2 = [(idx + 1, *stat2) for idx, stat2 in enumerate(stats2)]


        return self.render('admin/chart.html', stats=stats, now=datetime.now(),selected_month=month,
                           selected_year=year,stats2=stats2)


class LapHoaDon(AuthenticatedBaseView):
    required_permission = "create_order"  # Quyền cần thiết

    def is_accessible(self):
        return current_user.is_authenticated and current_user.role.name in ["Sales", "Admin"]

    @expose("/")
    def index(self):
        data = dao.load_book()
        user = dao.load_User()
        return self.render('admin/laphoadon.html', data=data, user=user)


class LapPhieuNhap(AuthenticatedBaseView):
    required_permission = "create_import_slip"  # Quyền cần thiết

    def is_accessible(self):
        return current_user.is_authenticated and current_user.role.name in ["Storekeeper", "Admin"]

    @expose("/")
    def index(self):
        data = dao.load_book()
        min_import_quantity, max_stock_for_import = dao.get_import_rules()
        return self.render('admin/lapphieunhap.html', data=data, min_import_quantity=min_import_quantity
                           , max_stock_for_import=max_stock_for_import)


class ThayDoiQuyDinh(AuthenticatedView):
    required_permission = "change_configuration"  # Quyền cần thiết
    column_display_pk = True
    column_hide_backrefs = False
    page_size = 20
    can_view_details = True


class CategoryView(AuthenticatedView):
    required_permission = "manage_categories"  # Quyền cần thiết
    column_formatters = {
        'image': _image_formatter,  # Áp dụng formatter vào cột "image"
    }
    column_list = ['id', 'name', 'image']

    form_extra_fields = {
        'image': FileField('Upload Image')
    }

    def on_model_change(self, form, model, is_created):
        """Xử lý tải ảnh lên Cloudinary khi thêm/sửa category."""
        file_data = form.image.data
        if file_data:
            # Tải ảnh lên Cloudinary
            upload_result = cloudinary.uploader.upload(file_data, folder='category_images')
            model.image = upload_result['secure_url']  # Lưu URL ảnh vào cột `image`


class BookView(AuthenticatedView):
    required_permission = "manage_books"  # Quyền cần thiết
    column_formatters = {
        'description': _truncate_formatter,  # Áp dụng formatter vào cột "description"
        'image': _image_formatter,  # Áp dụng formatter vào cột "image"
    }
    column_list = ['id', 'name', 'image', 'standard_price', 'discount', 'unit_price', 'available_quantity',
                   'description', 'categories', 'publisher', 'year_publishing']
    form_create_rules = [
        'name', 'standard_price', 'unit_price', 'is_enable', 'image', 'description', 'publisher', 'categories',
        'year_publishing']
    form_edit_rules = [
        'name', 'standard_price', 'unit_price', 'is_enable', 'image', 'description', 'publisher', 'categories',
        'year_publishing']
    column_filters = ['name']
    column_searchable_list = ['name']

    form_extra_fields = {
        'image': FileField('Upload Image')
    }

    def on_model_change(self, form, model, is_created):
        """Xử lý tải ảnh lên Cloudinary khi thêm/sửa sách."""
        file_data = form.image.data
        if file_data:
            # Tải ảnh mới lên Cloudinary
            upload_result = cloudinary.uploader.upload(file_data, folder='book_images')
            model.image = upload_result['secure_url']  # Lưu URL vào cột `image`


class UserView(AuthenticatedView):
    required_permission = "manage_users"  # Quyền cần thiết
    column_formatters = {
        'avatar_file': _image_formatter,  # Áp dụng formatter vào cột "image"
    }
    column_list = ['id', 'first_name', 'last_name', 'email', 'phone', 'birth', 'gender', 'avatar_file',
                   'active', 'role']

    form_excluded_columns = ['role_id', 'customer_orders', 'employee_orders'
        , 'reviews', 'import_tickets', 'vouchers', 'permission', 'favourite_books'
        , 'created_at', 'updated_at', 'address_id']

    form_extra_fields = {
        'avatar_file': FileField('Avatar')}  # Thêm trường tải ảnh

    def on_model_change(self, form, model, is_created):
        """Tải ảnh lên Cloudinary và lưu URL vào avatar_file."""
        file_data = form.avatar_file.data
        if file_data:
            # Tải ảnh lên Cloudinary
            upload_result = cloudinary.uploader.upload(file_data, folder='user_avatars')
            model.avatar_file = upload_result['secure_url']  # Lưu URL ảnh vào DB


class OrderView(AuthenticatedView):
    required_permission = "manage_orders"  # Quyền cần thiết
    column_list = ['employee_id', 'customer_id', 'received_money', 'paid_date', 'delivered_date', 'payment_method_id']
    form_create_rules = ['employee', 'customer', 'received_money', 'paid_date', 'delivered_date', 'payment_method']
    form_edit_rules = ['employee', 'customer', 'received_money', 'paid_date', 'delivered_date', 'payment_method']


class ReviewView(AuthenticatedView):
    required_permission = "manage_review"  # Quyền cần thiết
    column_list = ['id', 'rating', 'comment', 'user_id','book_id']
    form_excluded_columns = ['created_at', 'updated_at']
    form_create_rules = ['rating', 'comment', 'user','book']
    form_edit_rules = ['rating', 'comment', 'user','book']


class RoleHasPermissionView(AuthenticatedView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role.name in ["Admin"]

    column_list = ['role', 'permission']
    column_searchable_list = ['role.name', 'permission.name']
    # Cột sắp xếp
    column_sortable_list = ['role', 'permission']

    def _role_name(self, context, model, name):  # Thêm self parameter
        return model.role.name if model.role else None

    def _permission_name(self, context, model, name):  # Thêm self parameter
        return model.permission.name if model.permission else None

    column_formatters = {
        'role': _role_name,
        'permission': _permission_name
    }
    # Form fields
    form = type('RoleHasPermissionForm', (Form,), {
        'role': QuerySelectField(
            'Chọn vai trò',
            query_factory=lambda: Role.query.all(),
            get_label='name'
        ),
        'permission': QuerySelectField(
            'Chọn quyền',
            query_factory=lambda: Permission.query.all(),
            get_label='name'
        )
    })
    # Cấu hình form
    form_create_rules = [
        rules.Field('role'),
        rules.Field('permission')
    ]


class MyAdminView(AdminIndexView):
    @expose('/')
    def index(self):
        return self.render('admin/index.html')


admin = Admin(app=app, name="BookStore3H", template_mode="bootstrap4", index_view=MyAdminView())
admin.add_view(CategoryView(Category, db.session))
admin.add_view(BookView(Book, db.session))
admin.add_view(OrderView(Order, db.session))
admin.add_view(ReviewView(Review, db.session))
admin.add_view(UserView(User, db.session))
admin.add_view(ThayDoiQuyDinh(Configuration, db.session))
admin.add_view(RoleHasPermissionView(RoleHasPermission, db.session))
admin.add_view(LapHoaDon(name="Lập Hóa Đơn"))
admin.add_view(LapPhieuNhap(name="Lập Phiếu Nhập"))
admin.add_view(StatsView(name="Thống Kê"))
admin.add_view(LogoutView(name="Đăng Xuất"))
