### PR style

* does the PR have a descriptive title that starts with an uppercase letter?
* Does the PR clearly explain the problem that it is solving, and is that a good problem to solve?
* Does the PR show proof of the changes being well tested?
* If the PR is fixing an issue, is that issue clearly explained with error logs (inlined or linked), links to related github issues, etc.?
* Is the PR too large / could it be split into smaller more incremental PRs?
* If the PR includes a revert, is there sufficient justification?
* If a roll forward, does it explain what was fixed?
* Does the PR have an appropriate set of reviewers?
* Check to git blame layer for recent changes to affected files and who authored or reviewed those changes.

### Code style

* follow the style guides
* use descriptive variable names
* ensure comments are useful
* no typos

### Testing

* is the code covered by existing tests?
* Should new tests be added?
* Could the code be refactored into separate files, functions, etc. to better enable testing?
* How long do the tests take?
* Does the PR description include a quantitative analysis (# of tests, time taken)?
* Are the tests easy enough to run locally or are they overly reliant on GitHub workflows?

### Catching bugs

* If a variable or file name was changed, were all other references to that name changed across the project?

### Documentation

* Extract some tips from the Google technical writing style guide: https://developers.google.com/style
* Do code blocks have syntax hints?
* Information density: is the common/happy path easy to recognize and follow?
* If there are branches in the instructions (e.g. per operating system or GPU type), could they be removed or made more similar with some changes to the software?

### Notable types of PRs

#### New build dependency or subproject

* binary size diff?
* Time to build in logs?
* Any special considerations for packaging?

### Security

* no GitHub secrets
* use scoped and well-named roles
* limit permissions to read if possible
