/**
 * This is a minimal config.
 *
 * If you need the full config, get it from here:
 * https://unpkg.com/browse/tailwindcss@latest/stubs/defaultConfig.stub.js
 */

const defaultTheme = require('tailwindcss/defaultTheme')
const child_process = require('child_process')
const python_exe = process.env.PYTHON_EXE ?? 'python3'
const manage_py = process.env.MANAGE_PY ?? '../../manage.py'
const django_out = child_process.execSync(`${python_exe} ${manage_py} exporttheme`, {encoding: 'utf8'})
const django_theme_config = JSON.parse(django_out)

module.exports = {
  content: [
    /**
     * HTML. Paths to Django template files that will contain Tailwind CSS classes.
     */

    /*  Templates within theme app (<tailwind_app_name>/templates), e.g. base.html. */
    "../templates/**/*.html",

    /*
     * Main templates directory of the project (BASE_DIR/templates).
     * Adjust the following line to match your project structure.
     */
    "../../templates/**/*.html",

    /*
     * Templates in other django apps (BASE_DIR/<any_app_name>/templates).
     * Adjust the following line to match your project structure.
     */
    "../../**/templates/**/*.html",

    /**
     * JS: If you use Tailwind CSS in JavaScript, uncomment the following lines and make sure
     * patterns match your project structure.
     */
    /* JS 1: Ignore any JavaScript in node_modules folder. */
    // '!../../**/node_modules',
    /* JS 2: Process all JavaScript files in the project. */
    // '../../**/*.js',

    /**
     * Python: If you use Tailwind CSS classes in Python, uncomment the following line
     * and make sure the pattern below matches your project structure.
     */
    // '../../**/*.py'
  ],
  safelist: [
    "col-span-2"
  ],
  theme: {
    extend: {
      colors: {
        primary: django_theme_config.primary ?? "#C2000B",
        secondary: django_theme_config.secondary ?? "#111111",
      },
    },
    fontFamily: {
      header: ["BebasNeuePro-SemiExpBold", "Bebas Neue Pro", ...defaultTheme.fontFamily.sans],
    },
  },
  plugins: [
    /**
     * '@tailwindcss/forms' is the forms plugin that provides a minimal styling
     * for forms. If you don't like it or have own styling for forms,
     * comment the line below to disable '@tailwindcss/forms'.
     */
    require("@tailwindcss/forms"),
    require("@tailwindcss/typography"),
    require("@tailwindcss/line-clamp"),
    require("@tailwindcss/aspect-ratio"),
  ],
};
