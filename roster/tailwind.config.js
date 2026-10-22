import frappeUIPreset from "frappe-ui/src/tailwind/preset";
export default {
	presets: [frappeUIPreset],
	content: [
		"./index.html",
		"./src/**/*.{vue,js,ts,jsx,tsx}",
		"./node_modules/frappe-ui/src/components/**/*.{vue,js,ts,jsx,tsx}",
		"../node_modules/frappe-ui/src/components/**/*.{vue,js,ts,jsx,tsx}",
	],
	theme: {
		extend: {
			colors: {
				thread: {
					DEFAULT: "#2B59D1",
					dark: "#2449B0",
					glow: "rgba(43, 89, 209, 0.3)",
				},
				ink: {
					DEFAULT: "#111111",
					2: "#454545",
					3: "#5F5F5F",
				},
			},
		},
	},
	plugins: [],
};
