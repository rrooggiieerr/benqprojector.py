/** @type {import("prettier").Config} */
module.exports = {
  overrides: [
    {
      files: "./**/*.json",
      options: {
        plugins: [require.resolve("prettier-plugin-sort-json")],
        jsonRecursiveSort: true,
        jsonSortOrder: JSON.stringify({ [/.*/]: "numeric" }),
      },
    },
    {
      files: ["benqprojector/configs/*.json"],
      options: {
        useTabs: true,
        printWidth: 1,
        // commands should stay at the top
        jsonSortOrder: JSON.stringify({
          commands: null,
          [/.*/]: "numeric",
        }),
      },
    },
  ],
};
