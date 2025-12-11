const https = require('https');

module.exports = async ({ issueKey, comment, transition, baseUrl, email, token }) => {
    if (!issueKey) {
        console.log("Skipping Jira action: No issueKey provided.");
        return;
    }
    if (!baseUrl || !email || !token) {
        console.error("Skipping Jira action: Missing credentials (JIRA_BASE_URL, JIRA_USER_EMAIL, JIRA_API_TOKEN).");
        return;
    }

    const auth = Buffer.from(`${email}:${token}`).toString('base64');
    const urlObj = new URL(baseUrl.startsWith('http') ? baseUrl : `https://${baseUrl}`);

    // 1. Post Comment (if provided)
    if (comment) {
        // Parse Markdown Links [text](url)
        const contentNodes = [];
        const regex = /\[(.*?)\]\((.*?)\)/g;
        let lastIndex = 0;
        let match;

        while ((match = regex.exec(comment)) !== null) {
            if (match.index > lastIndex) {
                contentNodes.push({ type: "text", text: comment.substring(lastIndex, match.index) });
            }
            contentNodes.push({ type: "text", text: match[1], marks: [{ type: "link", attrs: { href: match[2] } }] });
            lastIndex = regex.lastIndex;
        }
        if (lastIndex < comment.length) {
            contentNodes.push({ type: "text", text: comment.substring(lastIndex) });
        }

        const data = JSON.stringify({
            body: {
                type: "doc",
                version: 1,
                content: [{ type: "paragraph", content: contentNodes }]
            }
        });

        const options = {
            hostname: urlObj.hostname,
            path: `/rest/api/3/issue/${issueKey}/comment`,
            method: 'POST',
            headers: {
                'Authorization': `Basic ${auth}`,
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(data)
            }
        };

        await new Promise((resolve) => {
            const req = https.request(options, (res) => {
                let body = '';
                res.on('data', (chunk) => body += chunk);
                res.on('end', () => {
                    if (res.statusCode >= 200 && res.statusCode < 300) {
                        console.log(`Jira comment posted to ${issueKey}`);
                    } else {
                        console.error(`Failed to post Jira comment: ${res.statusCode} ${body}`);
                    }
                    resolve();
                });
            });
            req.on('error', (e) => {
                console.error(`Error posting Jira comment: ${e.message}`);
                resolve();
            });
            req.write(data);
            req.end();
        });
    }

    // 2. Transition Issue (if provided)
    if (transition) {
        console.log(`Attempting to transition ${issueKey} to '${transition}'...`);

        // Step A: Get Transitions
        const transOptions = {
            hostname: urlObj.hostname,
            path: `/rest/api/3/issue/${issueKey}/transitions`,
            method: 'GET',
            headers: { 'Authorization': `Basic ${auth}` }
        };

        const transitions = await new Promise((resolve) => {
            const req = https.request(transOptions, (res) => {
                let body = '';
                res.on('data', (chunk) => body += chunk);
                res.on('end', () => {
                    if (res.statusCode === 200) {
                        try {
                            resolve(JSON.parse(body).transitions || []);
                        } catch (e) {
                            console.error("Failed to parse transitions response");
                            resolve([]);
                        }
                    } else {
                        console.error(`Failed to fetch transitions: ${res.statusCode} ${body}`);
                        resolve([]);
                    }
                });
            });
            req.on('error', () => resolve([]));
            req.end();
        });

        const targetTransition = transitions.find(t => t.name.toLowerCase() === transition.toLowerCase());

        if (targetTransition) {
            // Step B: Post Transition
            const transData = JSON.stringify({ transition: { id: targetTransition.id } });
            const postTransOptions = {
                hostname: urlObj.hostname,
                path: `/rest/api/3/issue/${issueKey}/transitions`,
                method: 'POST',
                headers: {
                    'Authorization': `Basic ${auth}`,
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(transData)
                }
            };

            await new Promise((resolve) => {
                const req = https.request(postTransOptions, (res) => {
                    let body = '';
                    res.on('data', (chunk) => body += chunk);
                    res.on('end', () => {
                        if (res.statusCode === 204) {
                            console.log(`Successfully transitioned ${issueKey} to '${transition}'`);
                        } else {
                            console.error(`Failed to transition issue: ${res.statusCode} ${body}`);
                        }
                        resolve();
                    });
                });
                req.on('error', (e) => {
                    console.error(`Error transitioning issue: ${e.message}`);
                    resolve();
                });
                req.write(transData);
                req.end();
            });
        } else {
            console.error(`Transition '${transition}' not found. Available: ${transitions.map(t => t.name).join(", ")}`);
        }
    }
};
