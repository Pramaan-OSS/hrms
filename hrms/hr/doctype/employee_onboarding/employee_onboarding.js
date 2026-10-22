// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Onboarding", {
	setup: function (frm) {
		frm.set_query("job_offer", function () {
			return {
				filters: {
					status: "Accepted",
					docstatus: 1,
				},
			};
		});
	},

	refresh: function (frm) {
		add_pramaan_buttons(frm);
		if (frm.doc.employee) {
			frm.add_custom_button(
				__("Employee"),
				function () {
					frappe.set_route("Form", "Employee", frm.doc.employee);
				},
				__("View"),
			);
		}
		if (frm.doc.project) {
			frm.add_custom_button(
				__("Project"),
				function () {
					frappe.set_route("Form", "Project", frm.doc.project);
				},
				__("View"),
			);
			frm.add_custom_button(
				__("Task"),
				function () {
					frappe.set_route("List", "Task", { project: frm.doc.project });
				},
				__("View"),
			);
		}
		if (!frm.doc.employee && frm.doc.docstatus === 1) {
			frm.add_custom_button(
				__("Employee"),
				function () {
					frappe.model.open_mapped_doc({
						method: "hrms.hr.doctype.employee_onboarding.employee_onboarding.make_employee",
						frm: frm,
					});
				},
				__("Create"),
			);
			frm.page.set_inner_btn_group_as_primary(__("Create"));
		}
		if (
			frm.doc.docstatus === 1 &&
			(frm.doc.boarding_status === "Pending" || frm.doc.boarding_status === "In Process")
		) {
			frm.add_custom_button(__("Mark as Completed"), function () {
				frm.trigger("mark_as_completed");
			});
		}
	},

	employee_onboarding_template: function (frm) {
		frm.set_value("activities", "");
		if (frm.doc.employee_onboarding_template) {
			frappe.call({
				method: "hrms.controllers.employee_boarding_controller.get_onboarding_details",
				args: {
					parent: frm.doc.employee_onboarding_template,
					parenttype: "Employee Onboarding Template",
				},
				callback: function (r) {
					if (r.message) {
						r.message.forEach((d) => {
							frm.add_child("activities", d);
						});
						refresh_field("activities");
					}
				},
			});
		}
	},

	job_offer: function (frm) {
		if (frm.doc.job_offer) {
			frappe.db.get_value("Employee", { job_offer: frm.doc.job_offer }, "name", (r) => {
				frm.set_value("employee", r && r.name ? r.name : "");
			});
		} else {
			frm.set_value("employee", "");
		}
	},

	mark_as_completed(frm) {
		frm.call({
			method: "mark_onboarding_as_completed",
			doc: frm.doc,
			freeze: true,
			freeze_message: __("Completing onboarding"),
		}).then((r) => {
			frm.refresh();
		});
	},
});

const add_pramaan_buttons = function (frm) {
	if (frm.is_new()) return;
	frm.add_custom_button(__("Start Identity Verification"), () => {
		hrms.pramaan.review_dialog({
			title: __("Start Identity Verification"),
			fields: [
				{
					fieldname: "end_user_id",
					fieldtype: "Data",
					label: __("Verification reference for the person"),
					reqd: 1,
				},
			],
			primary_label: __("Start"),
			on_apply: (values) => {
				hrms.pramaan.call(
					"hrms.integrations.pramaan_checks.start_identity_verification",
					{ employee_onboarding: frm.doc.name, end_user_id: values.end_user_id }
				).then((result) => {
					if (!result) return;
					if (result.url) {
						frappe.msgprint({
							title: __("Verification Started"),
							indicator: "green",
							message: __(
								"Send this private link to the person. The decision is read back afterwards."
							) + `<br><br>${frappe.utils.escape_html(result.url)}`,
						});
					}
				});
			},
		});
	});
};
