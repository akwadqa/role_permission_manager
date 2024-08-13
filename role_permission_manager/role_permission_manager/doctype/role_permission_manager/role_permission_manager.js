// Copyright (c) 2024, Akwad Programming and contributors
// For license information, please see license.txt

frappe.ui.form.on("Role Permission Manager", {
	refresh(frm) {
        frm.set_query("role", function () {
			return {
				filters: {
					is_custom: 1,
					disabled: 0,
					desk_access: 1,
				},
			};
		});

        frm.set_query("document_type", "document_type_permissions", function () {
			return {
				filters: {
					istable: 0,
				},
			};
		});

        frm.set_query("document_type", "document_type_select_permissions", function () {
			return {
				filters: {
					istable: 0,
				},
			};
		});

        frm.set_query("resource_name", "page_and_report_permissions", function (doc, cdt, cdn) {
            let row = locals[cdt][cdn];
            if (row.resource_type === "Page") {
                return {
                    filters: {
                        system_page: 0,
                    },
                };
            }
		});

        frm.add_custom_button(__('Get All Permissions'), function(){
            frappe.call({
                method: 'role_permission_manager.role_permission_manager.doctype.role_permission_manager.role_permission_manager.get_all_permissions',
                args: {
					rpm: frm.doc.name,
                    is_button: 1
                },
                callback: function(r) {
                    if (r.message) {
                        if (r.message.all_permissions) {
                            frm.set_value('document_type_permissions', r.message.all_permissions.permissions);
                            frm.set_value('page_and_report_permissions', r.message.all_permissions.page_and_report_permissions);
                            frm.save()
                        }
                        frappe.show_alert({
                            indicator: r.message.indicator,
                            message: r.message.message
                        }, 5);
                    }
                }
            });
        });
    },

    after_save(frm) {
        if (removed_permissions.length > 0) {
            frappe.call({
                method: 'role_permission_manager.role_permission_manager.doctype.role_permission_manager.role_permission_manager.remove_permissions_for_page_and_report',
                args: {
                    permissions: removed_permissions,
                    role: frm.doc.role
                },
                callback: function(r) {
                    if (r.message) {
                        frappe.show_alert({
                            indicator: r.message.indicator,
                            message: r.message.message
                        }, 5);
                    } 
                }
            });
            removed_permissions = [];
        }
    }
});


let removed_permissions = [];
frappe.ui.form.on("Permission for Page and Report", {
    resource_type: function(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, "resource_name", "");
    },

    before_page_and_report_permissions_remove: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        removed_permissions.push(row);
    }
});