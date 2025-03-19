// script.js
const collectionPaths = [
    '../tx/c1',
    '../tx/c2',
    '../tx/c3'
];

async function getRandomArticles() {
    try {
        const selectedArticles = [];
        
        for (const collectionPath of collectionPaths) {
            const response = await fetch(`${collectionPath}/filelist.txt`);
            const fileList = await response.text();
            const files = fileList.split('\n').filter(f => f);

            const randomFile = files[Math.floor(Math.random() * files.length)];
            const articleResponse = await fetch(`${collectionPath}/${randomFile}`);
            const article = await articleResponse.json();
            
            selectedArticles.push(article);
        }

        return {
            post1: selectedArticles[0],
            post2: selectedArticles[1],
            post3: selectedArticles[2]
        };
    } catch (error) {
        console.error('加载文章失败:', error);
        return getFallbackArticles();
    }
}

async function getDailyPosts() {
    const today = new Date().toDateString();
    const storedData = localStorage.getItem('dailyPosts');
    
    if (storedData) {
        const data = JSON.parse(storedData);
        if (data.date === today) return data.posts;
    }

    const newPosts = await getRandomArticles();
    
    localStorage.setItem('dailyPosts', JSON.stringify({
        date: today,
        posts: newPosts
    }));

    return newPosts;
}

function showFullArticle(postKey) {
    document.body.classList.add('modal-open');
    const posts = JSON.parse(localStorage.getItem('dailyPosts')).posts;
    const article = posts[postKey];
    
    document.getElementById('modalTitle').textContent = article.title;
    document.getElementById('modalContent').textContent = article.fullContent;
    document.getElementById('articleModal').style.display = 'block';
}

function closeModal() {
    document.getElementById('articleModal').style.display = 'none';
    document.body.classList.remove('modal-open');
}

window.onclick = function(event) {
    const modal = document.getElementById('articleModal');
    if (event.target === modal) {
        modal.style.display = 'none';
        document.body.classList.remove('modal-open');
    }
}

async function renderPosts() {
    const posts = await getDailyPosts();
    const contentDiv = document.getElementById('content');
    const dateInfoDiv = document.getElementById('dateInfo');
    
    dateInfoDiv.textContent = `更新日期：${new Date().toLocaleDateString()}`;

    contentDiv.innerHTML = `
        <div class="post">
            <h2>${posts.post1.title}</h2>
            <p>${posts.post1.content}</p>
            <a href="javascript:void(0)" class="read-more" onclick="showFullArticle('post1')">阅读全文 →</a>
        </div>
        <div class="post">
            <h2>${posts.post2.title}</h2>
            <p>${posts.post2.content}</p>
            <a href="javascript:void(0)" class="read-more" onclick="showFullArticle('post2')">阅读全文 →</a>
        </div>
        <div class="post">
            <h2>${posts.post3.title}</h2>
            <p>${posts.post3.content}</p>
            <a href="javascript:void(0)" class="read-more" onclick="showFullArticle('post3')">阅读全文 →</a>
        </div>
    `;
}

// 初始化
window.onload = renderPosts;