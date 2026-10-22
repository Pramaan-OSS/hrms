// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.tour["HR Settings"] = [
	{
		fieldname: "emp_created_by",
		title: "Employee Naming By",
		description: __(
			"Employee can be named by Employee ID if you assign one, or via Naming Series. Select your preference here.",
		),
	},
	{
		fieldname: "standard_working_hours",
		title: "Standard Working Hours",
		description: __(
			"Enter the Standard Working Hours for a normal work day. These hours will be used in calculations of reports such as Employee Hours Utilization and Project Profitability analysis.",
		),
	},
	{
		fieldname: "leave_and_expense_claim_settings",
		title: "Leave and Expense Claim Settings",
		description: __(
			"Review various other settings related to Employee Leaves and Expense Claim",
		),
	},
];

frappe.ui.form.on("HR Settings", {
	refresh(frm) {
		if (!frm.perm?.some((permission) => permission.write)) return;
		frm.add_custom_button(__("Connect Calendar"), () => {
			hrms.pramaan.call("hrms.integrations.pramaan_connections.connect_calendar", {}).then((result) => {
				if (!result) return;
				frappe.msgprint({
					title: __("Connect Calendar"),
					message: `<a href="${frappe.utils.escape_html(result.connect_url)}" target="_blank" rel="noopener noreferrer">${__("Continue connection")}</a>`,
				});
			});
		});
	},
});
