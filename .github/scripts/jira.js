const https = require('https');

module.exports = async ({ issueKey, comment, baseUrl, email, token }) => {
    if (!issueKey) {
        console.log("Skipping Jira comment: No issueKey provided.");
        return;
    }
    if (!baseUrl || !email || !token) {
        console.error("Skipping Jira comment: Missing credentials (JIRA_BASE_URL, JIRA_USER_EMAIL, JIRA_API_TOKEN).");
        return;
    }

    const auth = Buffer.from(`${email}:${token}`).toString('base64');

    // Parse Markdown Links [text](url)
    const contentNodes = [];
    const regex = /\[(.*?)\]\((.*?)\)/g;
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(comment)) !== null) {
        // Add text before the link
        if (match.index > lastIndex) {
            contentNodes.push({
                type: "text",
                text: comment.substring(lastIndex, match.index)
            });
        }
        // Add the link
        contentNodes.push({
            type: "text",
            text: match[1],
            marks: [{ type: "link", attrs: { href: match[2] } }]
        });
        lastIndex = regex.lastIndex;
    }
    // Add remaining text
    if (lastIndex < comment.length) {
        contentNodes.push({
            type: "text",
            text: comment.substring(lastIndex)
        });
    }

    const data = JSON.stringify({
        body: {
            type: "doc",
            version: 1,
            content: [
                {
                    type: "paragraph",
                    content: contentNodes
                }
            ]
        }
    });

    // Handle both full URLs and hostname only
    const urlObj = new URL(baseUrl.startsWith('http') ? baseUrl : `https://${baseUrl}`);

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

    return new Promise((resolve, reject) => {
        const req = https.request(options, (res) => {
            let body = '';
            res.on('data', (chunk) => body += chunk);
            res.on('end', () => {
                if (res.statusCode >= 200 && res.statusCode < 300) {
                    console.log(`Jira comment posted to ${issueKey}`);
                    resolve(body);
                } else {
                    console.error(`Failed to post Jira comment: ${res.statusCode} ${body}`);
                    // Don't fail the workflow, just log error
                    resolve(null);
                }
            });
        });

        req.on('error', (e) => {
            console.error(`Error posting Jira comment: ${e.message}`);
            resolve(null);
        });

        req.write(data);
        req.end();
    });
};
