# Copyright (c) 2024, Akwad Programming and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_link_to_form
from frappe.permissions import add_permission, setup_custom_perms
import time
import json

PROGRESS_TITLE = _("Updating Permissions")
PROGRESS_DESCRIPTION = _("Please wait. This may take a few minutes...")


class RolePermissionManager(Document):
	def before_insert(self):
		get_all_permissions(self)


	def on_trash(self):
		self.remove_all_permissions()


	def validate(self):
		frappe.publish_progress(percent=1, title=PROGRESS_TITLE, description=PROGRESS_DESCRIPTION)
		time.sleep(0.5)
		self.add_select_perm_doctypes()


	def on_update(self):
		self.validate_role()
		self.add_role_permissions_for_user_doctypes()
		self.add_role_permissions_for_select_doctypes()
		self.add_role_permissions_for_file()
		self.add_permissions_for_page_and_report()
		self.remove_permission_for_deleted_doctypes()


	def validate_role(self):
		if not self.role:
			frappe.throw(_("The field {0} is mandatory").format(frappe.bold(_("Role"))))

		if not frappe.db.get_value("Role", self.role, "is_custom"):
			frappe.throw(
				_("The role {0} should be a custom role.").format(
					frappe.bold(get_link_to_form("Role", self.role))
				)
			)

	
	def add_role_permissions_for_user_doctypes(self):
		perms = ["read", "write", "create", "submit", "cancel", "amend", "delete", "if_owner", "report", "export", "import", "share", "print", "email"]
		
		total_count = len(self.document_type_permissions) if self.document_type_permissions else None
		if not total_count:
			frappe.publish_progress(
				percent=25, 
				title=PROGRESS_TITLE, 
				description=PROGRESS_DESCRIPTION
			)
			return
		progress_increment = 25 / total_count
		current_progress = 0

		for row in self.document_type_permissions:
			docperm = add_role_permissions(row.document_type, self.role)

			values = {perm: row.get(perm+"_perm") or 0 for perm in perms}

			frappe.db.set_value("Custom DocPerm", docperm, values)

			current_progress += progress_increment
			frappe.publish_progress(
				percent=current_progress, 
				title=PROGRESS_TITLE, 
				description=PROGRESS_DESCRIPTION
			)
	

	def add_select_perm_doctypes(self):
		self.document_type_select_permissions = []

		select_doctypes = []
		user_doctypes = [row.document_type for row in self.document_type_permissions]

		for doctype in user_doctypes:
			doc = frappe.get_meta(doctype)
			self.prepare_select_perm_doctypes(doc, user_doctypes, select_doctypes)

			for child_table in doc.get_table_fields():
				child_doc = frappe.get_meta(child_table.options)
				if child_doc:
					self.prepare_select_perm_doctypes(child_doc, user_doctypes, select_doctypes)

		if select_doctypes:
			select_doctypes = set(select_doctypes)
			for select_doctype in select_doctypes:
				self.append("document_type_select_permissions", {"document_type": select_doctype})


	def prepare_select_perm_doctypes(self, doc, user_doctypes, select_doctypes):
		for field in doc.get_link_fields():
			if field.options not in user_doctypes:
				select_doctypes.append(field.options)

	
	def add_role_permissions_for_select_doctypes(self):
		total_count = len(self.document_type_select_permissions) if self.document_type_select_permissions else None
		if not total_count:
			frappe.publish_progress(
				percent=50, 
				title=PROGRESS_TITLE, 
				description=PROGRESS_DESCRIPTION
			)
			return
		progress_increment = 25 / total_count
		current_progress = 25

		for row in self.document_type_select_permissions:
			docperm = add_role_permissions(row.document_type, self.role)
			frappe.db.set_value(
				"Custom DocPerm", docperm, {"select": 1, "read": 0, "create": 0, "write": 0}
			)

			current_progress += progress_increment
			frappe.publish_progress(
				percent=current_progress, 
				title=PROGRESS_TITLE, 
				description=PROGRESS_DESCRIPTION
			)

	
	def add_role_permissions_for_file(self):
		docperm = add_role_permissions("File", self.role)
		frappe.db.set_value("Custom DocPerm", docperm, {"read": 1, "create": 1, "write": 1})


	def remove_permission_for_deleted_doctypes(self):
		doctypes = [d.document_type for d in self.document_type_permissions]

		# Do not remove the doc permission for the file doctype
		doctypes.append("File")

		for doctype in ["document_type_select_permissions"]:
			doctypes.extend(dt.document_type for dt in self.get(doctype))
		
		perm_list = frappe.get_all(
			"Custom DocPerm", filters={"role": self.role, "parent": ["not in", doctypes]}
		)

		total_count = len(perm_list) if perm_list else None
		if not total_count:
			frappe.publish_progress(
				percent=100, 
				title=PROGRESS_TITLE, 
				description=PROGRESS_DESCRIPTION
			)
			return
		progress_increment = 25 / total_count
		current_progress = 75

		for index, perm in enumerate(perm_list):
			frappe.delete_doc("Custom DocPerm", perm.name)

			if index == total_count - 1:
				current_progress = 100
			else:
				current_progress += progress_increment
			frappe.publish_progress(
				percent=current_progress, 
				title=PROGRESS_TITLE, 
				description=PROGRESS_DESCRIPTION
			)


	def remove_all_permissions(self):
		# Document Type Permissions
		doctypes = [d.document_type for d in self.document_type_permissions]

		doctypes.append("File")

		for doctype in ["document_type_select_permissions"]:
			doctypes.extend(dt.document_type for dt in self.get(doctype))
			
		for perm in frappe.get_all(
			"Custom DocPerm", filters={"role": self.role, "parent": ["in", doctypes]}
		):
			frappe.delete_doc("Custom DocPerm", perm.name)

		# Other Permissions
		for permission in self.page_and_report_permissions:
			resource_type = permission.get("resource_type")
			resource_name = permission.get("resource_name")
			if frappe.db.exists("Custom Role", {resource_type.lower(): resource_name}):
				custom_role_doc = frappe.get_value("Custom Role", {resource_type.lower(): resource_name}, "name")
				if frappe.db.exists("Has Role", {"role": self.role, "parenttype": "Custom Role", "parent": custom_role_doc}):
					has_role = frappe.get_value("Has Role", {"role": self.role,  "parenttype": "Custom Role", "parent": custom_role_doc}, "name")
					frappe.delete_doc("Has Role", has_role)
	

	def add_permissions_for_page_and_report(self):
		total_count = len(self.page_and_report_permissions) if self.page_and_report_permissions else None
		if not total_count:
			frappe.publish_progress(
				percent=75, 
				title=PROGRESS_TITLE, 
				description=PROGRESS_DESCRIPTION
			)
			return
		progress_increment = 25 / total_count
		current_progress = 50

		for resource in self.page_and_report_permissions:
			resource_type = resource.get("resource_type")
			resource_name = resource.get("resource_name")
			if not frappe.db.exists("Custom Role", {resource_type.lower(): resource_name}):
				resource_doc = frappe.get_doc(resource_type, resource_name)
				custom_role_doc = frappe.new_doc(
					doctype = "Custom Role",
					page = resource_name if resource_type == "Page" else None,
					report = resource_name if resource_type == "Report" else None,
					ref_doctype = frappe.db.get_value("Report", resource_name, "ref_doctype") if resource_type == "Report" else None,
					roles = resource_doc.roles
				).insert()
			else:
				custom_role_doc = frappe.get_doc("Custom Role", {resource_type.lower(): resource_name})

			if not frappe.db.exists("Has Role", {"role": self.role, "parenttype": "Custom Role", "parent": custom_role_doc.name}):
				custom_role_doc.append('roles', {'role': self.role})
				custom_role_doc.save()

			current_progress += progress_increment
			frappe.publish_progress(
				percent=current_progress, 
				title=PROGRESS_TITLE, 
				description=PROGRESS_DESCRIPTION
			)


def add_role_permissions(doctype, role):
	name = frappe.get_value("Custom DocPerm", dict(parent=doctype, role=role, permlevel=0))

	if not name:
		name = add_permission(doctype, role, 0)

	return name





@frappe.whitelist()
def get_all_permissions(rpm, is_button=0):
	if is_button:
		rpm_doc = frappe.get_doc("Role Permission Manager", rpm)
	else:
		rpm_doc = rpm

	doctype_list = frappe.get_all(
		doctype = "DocPerm",
		filters = {"role": rpm_doc.role},
		pluck = "parent"
	)
	if doctype_list:
		for doctype in doctype_list:
			setup_custom_perms(doctype)
	
	permissions = get_permissions(rpm_doc)
	page_and_report_permissions = get_page_and_report_permissions(rpm_doc)
	
	if is_button:
		all_permissions = {
			"permissions": permissions,
			"page_and_report_permissions": page_and_report_permissions
		}
		if permissions or page_and_report_permissions:
			return {"indicator": "green", "message": _("Successful"), "all_permissions": all_permissions}
		else:
			return {"indicator": "red", "message": _("No permissions found"), "all_permissions": None}
	else:
		rpm_doc.set('document_type_permissions', permissions)
		rpm_doc.set('page_and_report_permissions', page_and_report_permissions)


def get_permissions(rpm_doc):
	permissions = []
	custom_docperm_list = frappe.get_all(
		doctype = "Custom DocPerm",
		filters = {"role": rpm_doc.role, "select": 0, "parent": ["!=", "File"]},
		fields = ["name", "parent", "read", "write", "create", "submit", "cancel", "amend", "delete", "if_owner", "report", "export", "import", "share", "print", "email"]
	)
	if custom_docperm_list:
		for custom_docperm in custom_docperm_list:
			permissions.append({
				"document_type": custom_docperm.get("parent"),
				"read_perm": custom_docperm.get("read"),
				"write_perm": custom_docperm.get("write"),
				"create_perm": custom_docperm.get("create"),
				"submit_perm": custom_docperm.get("submit"),
				"cancel_perm": custom_docperm.get("cancel"),
				"amend_perm": custom_docperm.get("amend"),
				"delete_perm": custom_docperm.get("delete"),
				"if_owner_perm": custom_docperm.get("if_owner"),
				"report_perm": custom_docperm.get("report"),
				"export_perm": custom_docperm.get("export"),
				"import_perm": custom_docperm.get("import"),
				"share_perm": custom_docperm.get("share"),
				"print_perm": custom_docperm.get("print"),
				"email_perm": custom_docperm.get("email")
			})
	return permissions


def get_page_and_report_permissions(rpm_doc):
	page_and_report_permissions = []
	
	page_and_report_list = frappe.get_all(
		doctype = "Has Role",
		filters = {"role": rpm_doc.role, "parenttype": ["in", ["Page", "Report"]]},
		fields = ["parent", "parenttype"]
	)
	if page_and_report_list:
		for resource in page_and_report_list:
			parenttype = resource.get("parenttype")
			parent = resource.get("parent")
			if not frappe.db.exists("Custom Role", {parenttype: parent}):
				resource_doc = frappe.get_doc(parenttype, parent)
				frappe.new_doc(
					doctype = "Custom Role",
					page = parent if parenttype == "Page" else None,
					report = parent if parenttype == "Report" else None,
					ref_doctype = frappe.db.get_value("Report", parent, "ref_doctype") if parenttype == "Report" else None,
					roles = resource_doc.roles
				).insert()

	custom_role_list = frappe.get_all(
		doctype = "Has Role",
		filters = {"role": rpm_doc.role, "parenttype": "Custom Role"},
		pluck = "parent"
	)
	if custom_role_list:
		for custom_role in custom_role_list:
			custom_role_doc = frappe.get_doc("Custom Role", custom_role)
			page = custom_role_doc.page
			report = custom_role_doc.report
			page_and_report_permissions.append({
				"resource_type": "Page" if page else "Report",
				"resource_name": page if page else report
			})

	return page_and_report_permissions


@frappe.whitelist()
def remove_permissions_for_page_and_report(permissions, role):
	for permission in json.loads(permissions):
		resource_type = permission.get("resource_type")
		resource_name = permission.get("resource_name")
		if frappe.db.exists("Custom Role", {resource_type.lower(): resource_name}):
			custom_role_doc = frappe.get_value("Custom Role", {resource_type.lower(): resource_name}, "name")
			if frappe.db.exists("Has Role", {"role": role, "parenttype": "Custom Role", "parent": custom_role_doc}):
				has_role = frappe.get_value("Has Role", {"role": role,  "parenttype": "Custom Role", "parent": custom_role_doc}, "name")
				frappe.delete_doc("Has Role", has_role)
				# frappe.delete_doc("Has Role", has_role, force=True, ignore_permissions=True)
	
	return {"indicator": "green", "message": _("Page and Report Permissions Removed")}