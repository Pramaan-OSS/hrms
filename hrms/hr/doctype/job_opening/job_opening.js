// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Job Opening", {
	onload: function (frm) {
		frm.set_query("department", function () {
			return {
				filters: {
					company: frm.doc.company,
				},
			};
		});
	},
	refresh: function (frm) {
		frm.trigger("add_status_toggle_button");
		frm.trigger("add_pramaan_buttons");
	},
	add_pramaan_buttons: function (frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Check Description"), () => {
			hrms.pramaan.call("hrms.integrations.pramaan_recruiting.analyze_description", {
				opening: frm.doc.name,
			}).then((result) => {
				if (!result) return;
				const analysis = result.analysis || {};
				const lines = [];
				if (analysis.title) lines.push(`<b>${__("Title")}</b>: ${frappe.utils.escape_html(analysis.title)}`);
				(analysis.skills || []).forEach((skill) =>
					lines.push(`<div>${__("Skill")}: ${frappe.utils.escape_html(skill)}</div>`)
				);
				if (analysis.salary_range)
					lines.push(`<b>${__("Salary range")}</b>: ${frappe.utils.escape_html(String(analysis.salary_range))}`);
				(analysis.warnings || analysis.warning_signs || []).forEach((warning) =>
					lines.push(`<div style="color:#b91c1c">${__("Warning")}: ${frappe.utils.escape_html(warning)}</div>`)
				);
				frappe.msgprint({
					title: __("Description Check"),
					indicator: "blue",
					message: lines.join("") || __("Nothing notable found in this description."),
				});
			});
		}, __("Insights"));

		frm.add_custom_button(__("Suggest Pay Range"), () => {
			hrms.pramaan.call("hrms.integrations.pramaan_recruiting.suggest_salary_range", {
				opening: frm.doc.name,
			}).then((result) => {
				if (!result) return;
				const distribution = result.distribution || {};
				const rows = (distribution.thresholds || [])
					.map((row) => `<li>${frappe.utils.escape_html(JSON.stringify(row))}</li>`)
					.join("");
				frappe.msgprint({
					title: __("Advertised Pay Distribution"),
					indicator: "blue",
					message: rows
						? `<ul>${rows}</ul>`
						: __("No advertised pay data is available for this role and location yet."),
				});
			});
		}, __("Insights"));

		frm.add_custom_button(__("Rank Applicants"), () => {
			hrms.pramaan.review_dialog({
				title: __("Rank Applicants Against This Opening"),
				fields: [
					{
						fieldname: "skills",
						fieldtype: "Small Text",
						label: __("Skill requirements (one per line, 1 to 10)"),
						reqd: 1,
					},
					{
						fieldname: "basis_ground",
						fieldtype: "Select",
						label: __("Candidate consent recorded as"),
						options: "consent\nlegitimate_interest\ncontract",
						default: "consent",
						reqd: 1,
					},
				],
				primary_label: __("Compare resumes"),
				on_apply: (values) => {
					const skills = values.skills
						.split("\n")
						.map((line) => line.trim())
						.filter(Boolean);
					hrms.pramaan.call(
						"hrms.integrations.pramaan_recruiting.rank_applicants",
						{ opening: frm.doc.name, skills, basis_ground: values.basis_ground }
					).then((result) => {
						if (!result) return;
						const report = hrms.pramaan.outcome_result(result.report);
						if (!report) return;
						const rows = (report.candidates || report.results || report.rows || [])
							.map((row) => `<li>${frappe.utils.escape_html(JSON.stringify(row))}</li>`)
							.join("");
						frappe.msgprint({
							title: __("Applicant Comparison"),
							indicator: "blue",
							message: rows
								? `<ul>${rows}</ul><p>${__("A person decides. Nobody is rejected automatically.")}</p>`
								: __("The comparison returned no rows. Check the resumes and try again."),
						});
					});
				},
			});
		}, __("Insights"));

		frm.add_custom_button(__("Draft Description"), () => {
			hrms.pramaan.call("hrms.integrations.pramaan_writing.draft_job_description", {
				opening: frm.doc.name,
			}).then((result) => {
				if (!result) return;
				hrms.pramaan.show_draft({
					title: __("Draft Job Description"),
					draft: result.draft,
					apply_label: __("Use this draft"),
					on_apply: (draft) => {
						frm.set_value("description", draft);
					},
				});
			});
		}, __("Insights"));
	},
	add_status_toggle_button: function (frm) {
		if (frm.is_new()) return;

		const is_open = frm.doc.status === "Open";
		const label = is_open ? __("Close Job Opening") : __("Reopen Job Opening");

		frm.add_custom_button(label, () => {
			frm.set_value("status", is_open ? "Closed" : "Open");
			frm.save();
		});
	},
	designation: function (frm) {
		if (frm.doc.designation) {
			frm.set_value("job_title", frm.doc.designation);
		}
		if (frm.doc.designation && frm.doc.company) {
			frappe.call({
				method: "hrms.hr.doctype.staffing_plan.staffing_plan.get_active_staffing_plan_details",
				args: {
					company: frm.doc.company,
					designation: frm.doc.designation,
					date: frappe.datetime.now_date(), // ToDo - Date in Job Opening?
				},
				callback: function (data) {
					if (data.message) {
						frm.set_value("staffing_plan", data.message[0].name);
						frm.set_value("planned_vacancies", data.message[0].vacancies);
					} else {
						frm.set_value("staffing_plan", "");
						frm.set_value("planned_vacancies", 0);
						frappe.show_alert({
							indicator: "orange",
							message: __("No Staffing Plans found for this Designation"),
						});
					}
				},
			});
		} else {
			frm.set_value("staffing_plan", "");
			frm.set_value("planned_vacancies", 0);
		}
	},
	company: function (frm) {
		frm.set_value("designation", "");
	},
	status: function (frm) {
		frm.close_warning_confirmed = false;
	},
	before_save: function (frm) {
		frm.trigger("confirm_close_if_needed");
	},
	after_save: function (frm) {
		frm.close_warning_confirmed = false;
	},
	confirm_close_if_needed: function (frm) {
		if (frm.is_new() || frm.close_warning_confirmed || frm.doc.status !== "Closed") {
			return;
		}

		frappe.validated = false;

		frm.call("get_close_warning").then((r) => {
			if (!r.message) {
				frm.close_warning_confirmed = true;
				frm.save();
				return;
			}

			frappe.confirm(r.message, () => {
				frm.close_warning_confirmed = true;
				frm.save();
			});
		});
	},

	job_opening_template: function (frm) {
		if (!frm.doc.job_opening_template) return;
		frappe.db.get_doc("Job Opening Template", frm.doc.job_opening_template).then((doc) => {
			frm.set_value({
				designation: doc.designation,
				department: doc.department,
				employment_type: doc.employment_type,
				location: doc.location,
				description: doc.description,
				currency: doc.currency,
				upper_range: doc.upper_range,
				lower_range: doc.lower_range,
				salary_per: doc.salary_per,
				publish_salary_range: doc.publish_salary_range,
			});

			frm.refresh_fields();
		});
	},
	publish: function (frm) {
		if (frm.doc.publish && !frm.doc.route) {
			frm.trigger("set_route");
		}
	},
	set_route: function (frm) {
		if (frm.doc.publish && !frm.doc.route) {
			route = `jobs/${frappe.scrub(frm.doc.company)}/${frappe.scrub(frm.doc.job_title)}`;
			frm.set_value("route", route);
		}
	},
});
