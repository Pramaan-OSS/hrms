frappe.provide("hrms.pramaan");

// Shared desk helper for the platform-backed actions. Every endpoint answers
// with { available, message, ... }: an unavailable feature shows its plain
// message and never a provider name.
hrms.pramaan.call = function (method, args, options = {}) {
	return new Promise((resolve) => {
		frappe.call({
			method,
			args,
			callback: (r) => {
				const result = r.message || {};
				if (result.available === false) {
					frappe.msgprint({
						title: options.unavailable_title || __("Not available yet"),
						indicator: "orange",
						message: result.message || __("This feature is not available yet."),
					});
					resolve(null);
					return;
				}
				resolve(result);
			},
		});
	});
};

hrms.pramaan.review_dialog = function ({ title, fields, primary_label, on_apply }) {
	const dialog = new frappe.ui.Dialog({
		title,
		fields,
		primary_action_label: primary_label,
		primary_action(values) {
			dialog.hide();
			on_apply(values, dialog);
		},
	});
	dialog.show();
	return dialog;
};

hrms.pramaan.show_draft = function ({ title, draft, apply_label, on_apply }) {
	hrms.pramaan.review_dialog({
		title,
		fields: [
			{
				fieldname: "draft",
				fieldtype: "Text Editor" in frappe.ui ? "Text Editor" : "Small Text",
				label: __("Draft"),
				default: draft,
			},
		],
		primary_label: apply_label,
		on_apply: (values) => on_apply(values.draft),
	});
};

hrms.pramaan.outcome_result = function (report) {
	if (report?.status !== "done" || !report.result || typeof report.result !== "object") {
		frappe.msgprint({
			title: __("Check incomplete"),
			indicator: "orange",
			message: __("This check did not complete. No conclusion was reached. Review its status before trying again."),
		});
		return null;
	}
	if (report.completeness === "partial") {
		frappe.show_alert({
			indicator: "orange",
			message: __("Only part of this check completed. Review which facts were not checked before drawing a conclusion."),
		});
	}
	return report.result;
};
